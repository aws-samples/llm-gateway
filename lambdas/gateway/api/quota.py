from fastapi import HTTPException, status
import datetime
import os
from cachetools import TTLCache
import boto3
from boto3.dynamodb.conditions import Key
import json
import pandas as pd
from botocore.exceptions import ClientError
import decimal

DEFAULT_QUOTA_PARAMETER_NAME = os.environ.get("DEFAULT_QUOTA_PARAMETER_NAME")
QUOTA_TABLE_NAME = os.environ.get("QUOTA_TABLE_NAME")
REGION = os.environ.get("REGION")

ssm_client = boto3.client("ssm")
dynamodb = boto3.resource('dynamodb')
quota_table = dynamodb.Table(QUOTA_TABLE_NAME)

cache = TTLCache(maxsize=5000, ttl=60)

cost_df = pd.read_csv('/app/api/data/cost_db.csv', dtype={'cost_per_token': float})
print(f'cost_df: {cost_df}')

def check_quota(user_name):
    print('Checking if user has exceeded usage quota')
    quota_config = get_from_cache(user_name)

    if not quota_config:
        print("No cached quota, getting user's quota config")
        quota_config = get_user_quota_config(user_name)
        
        if not quota_config:
            print('No user specific config, getting default quota config')
            quota_config = get_default_quota()
            if quota_config:
                print(f'Found default quota config: {quota_config}')
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Quota config not configured correctly"
                )
        else:
            print(f'Found user quota config: {quota_config}')

        add_to_cache(user_name, quota_config)
    else:
        print(f'Found cached quota config: {quota_config}')
    
    print(f'fetching requests_summary')
    requests_summary = get_user_requests_summary(user_name)
    print(f'requests_summary: {requests_summary}')

    if not requests_summary:
        print(f"Didn't find requests_summary, creating new one")
        new_requests_summary = build_new_requests_summary(user_name, quota_config)
        print(f"new_requests_summary: {new_requests_summary}")
        create_requests_summary(new_requests_summary)
    else:
        quota_limit_map = requests_summary.get('quota_limit_map', None)
        print(f'quota_limit_map: {quota_limit_map}')
        request_summary_needs_update = False
        for frequency, limit in quota_config.items():
            current_time_period = get_current_time_period(frequency)
            if frequency not in quota_limit_map or quota_limit_map[frequency]["time_period"] != current_time_period:
                quota_limit_map[frequency] = {
                    "time_period": current_time_period,
                    "total_estimate_cost": decimal.Decimal(str(0.00))
                }
                request_summary_needs_update = True
            else:
                if float(quota_limit_map[frequency]["total_estimate_cost"]) > float(limit):
                    print(f'Quota exceeded. Quota frequency: {frequency}. Total usage: {quota_limit_map[frequency]["total_estimate_cost"]}. Limit: {limit}')
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Quota exceeded. Quota frequency: {frequency}. Total usage: {quota_limit_map[frequency]["total_estimate_cost"]}. Limit: {limit}"
                    )
        if request_summary_needs_update:
            print(f'request summary needs update, updating...')
            update_requests_summary(requests_summary, quota_config, user_name)

    print(f'Quota is not exceeded. Processing request.')
    return requests_summary

def build_new_requests_summary(user_name, quota_config):
    try:
        quota_limit_map = {}
        for frequency, limit in quota_config.items():
            quota_limit_map[frequency] = {
                "time_period": get_current_time_period(frequency),
                "total_estimate_cost": decimal.Decimal(str(0.00))
            }
        requests_summary = {
            "username_document_type": user_name + ":requests_summary",
            "id": user_name,
            "quota_limit_map": quota_limit_map,
            'last_updated_time': get_current_timestamp()
        }
        return requests_summary
    except Exception as e:
        print(f'Failed to build new requests summary with error {e}')

def create_requests_summary(requests_summary):
    try:
        response = quota_table.put_item(
            Item=requests_summary,
            ConditionExpression='attribute_not_exists(username_document_type) AND attribute_not_exists(id)'
        )
        print("Item created successfully:", response)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            print("Item already exists. Continuing...")
        else:
            raise

def get_current_timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def update_requests_summary(requests_summary, quota_config, user_name):
    last_known_update_time = requests_summary["last_updated_time"]
    requests_summary["last_updated_time"] = get_current_timestamp()
    try:
        # Perform the put operation
        response = quota_table.put_item(
            Item=requests_summary,
            ConditionExpression="last_updated_time = :last_known_time",
            ExpressionAttributeValues={
                ':last_known_time': last_known_update_time
            }
        )
        print("Item successfully uploaded:", response)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            print("Upload failed: Last updated time has changed since last read. Reading the latest document and seeing if it still needs updating")
            latest_requests_summary = get_user_requests_summary(user_name)
            quota_limit_map = latest_requests_summary.get('quota_limit_map')

            request_summary_needs_update = False
            for frequency, limit in quota_config.items():
                current_time_period = get_current_time_period(frequency)
                if frequency not in quota_limit_map or quota_limit_map[frequency]["time_period"] != current_time_period:
                    quota_limit_map[frequency] = {
                        "time_period": current_time_period,
                        "total_estimate_cost": decimal.Decimal(str(0.00))
                    }
                    request_summary_needs_update = True
            if request_summary_needs_update:
                update_requests_summary(latest_requests_summary)
        else:
            raise

def get_current_time_period(frequency):
    if frequency == "weekly":
        today = datetime.date.today()
        start_of_week = today - datetime.timedelta(days=today.weekday())
        date_str = f"{start_of_week.year}-{start_of_week.month}-{start_of_week.day}"
        return date_str
    else:
        raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Quota Configuration has unsupported frequency type"
                )

def get_user_quota_config(user_name):
    quota_config_document = get_user_document(user_name, "quota_config")
    if quota_config_document:
        return quota_config_document.get('quota_map', None)

def get_user_requests_summary(user_name):
    return get_user_document(user_name, "requests_summary")

def get_user_document(user_name, document_type):
    username_document_type = user_name + f":{document_type}"
    id = user_name
    print(f'username_document_type: {username_document_type} id: {id}')

    response = quota_table.query(
        KeyConditionExpression=Key('username_document_type').eq(username_document_type) & Key('id').eq(id)
    )
    print(f'response: {response}')
    print(f'response: {response["Items"]}')
    print(f'not response["Items"]: {not response["Items"]}')
    if not response["Items"]:
        return None

    return response["Items"][0]

def add_to_cache(key, value):
    cache[key] = value

def get_from_cache(key):
    return cache.get(key, None)

def get_default_quota():
    response = ssm_client.get_parameter(Name=DEFAULT_QUOTA_PARAMETER_NAME, WithDecryption=True)
    parameter_value = response['Parameter']['Value']
    default_quota_config_dict = json.loads(parameter_value)
    return default_quota_config_dict

def calculate_input_cost(prompt_tokens, model):
    return calculate_cost(prompt_tokens, model, 'input')

def calculate_output_cost(completion_tokens, model):
    return calculate_cost(completion_tokens, model, 'output')

def calculate_cost(num_tokens, model, cost_type):
    print(f'cost_df: {cost_df}')
    print(f'model: {model} region: {REGION} type: {cost_type}')
    filtered_df = cost_df[
        (cost_df['model_name'] == model) & 
        ((cost_df['region'] == REGION) | (cost_df['region'].isna())) & 
        (cost_df['type'] == cost_type)
    ]
    print(f'filtered_df: {filtered_df}')
    costs_per_token = filtered_df.iloc[0]['cost_per_token']
    return (num_tokens * costs_per_token) / 1000

def update_quota(user_name, total_cost):
    keys = {
        'username_document_type': user_name + ":requests_summary",  # Partition Key
        'id': user_name    # Sort Key
    }

    try:
        response = quota_table.update_item(
            Key=keys,
            UpdateExpression="""
            ADD #qlm.#wk.#tec :inc""",
                #qlm.#hr.#tec :inc,
                #qlm.#dy.#tec :inc,
                #qlm.#mn.#tec :inc
            #""",
            ExpressionAttributeNames={
                "#qlm": "quota_limit_map",
                #"#hr": "hourly",
                #"#dy": "daily",
                "#wk": "weekly",
                #"#mn": "monthly",
                "#tec": "total_estimate_cost"
            },
            ExpressionAttributeValues={
                ":inc": decimal.Decimal(str(total_cost))
            },
            ReturnValues="UPDATED_NEW"
        )
        print("Update succeeded:", response)
    except Exception as e:
        print("Error updating item:", e)