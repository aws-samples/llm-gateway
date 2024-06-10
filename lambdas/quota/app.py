import boto3
import datetime
import json
import logging
import os
from botocore.exceptions import ClientError
from decimal import Decimal, DecimalException
from collections import defaultdict
from boto3.dynamodb.conditions import Key
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

## BEGIN ENVIORNMENT VARIABLES #################################################
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
# Chat history.
QUOTA_TABLE_NAME = os.environ.get("QUOTA_TABLE_NAME", None)
DEFAULT_QUOTA_PARAMETER_NAME = os.environ.get("DEFAULT_QUOTA_PARAMETER_NAME")
COGNITO_DOMAIN_PREFIX = os.environ.get("COGNITO_DOMAIN_PREFIX")
ssm_client = boto3.client("ssm")

REGION = os.environ.get("REGION")

class Settings:
    def __init__(self, event, session):
        self.dynamodb_client = boto3.client("dynamodb")
        # Get config from the request body.
        body = json.loads(event["body"])
        self.prompt = body["prompt"]

def can_convert_to_decimal(value):
    try:
        Decimal(value)
        return True
    except (DecimalException, TypeError, ValueError):
        return False

def get_default_quota():
    response = ssm_client.get_parameter(Name=DEFAULT_QUOTA_PARAMETER_NAME, WithDecryption=True)
    parameter_value = response['Parameter']['Value']
    default_quota_config_dict = json.loads(parameter_value)
    return default_quota_config_dict

def get_user_name(authorization_header):
    user_info = get_user_info_cognito(authorization_header)
    user_name = user_info["preferred_username"]
    return user_name

def get_user_info_cognito(authorization_header):
    url = f'https://{COGNITO_DOMAIN_PREFIX}.auth.{REGION}.amazoncognito.com/oauth2/userInfo'

    # Set the headers with the access token
    headers = {
        'Authorization': authorization_header
    }

    # Make the HTTP GET request to the User Info endpoint
    response = requests.get(url, headers=headers, timeout=60)

    # Check if the request was successful
    if response.status_code == 200:
        return response.json()  # Returns the user info as a JSON object
    else:
        return response.status_code, response.text  # Returns error status and message if not successful

def get_quota_summary(username, table, response):
    try:
        # Perform a query operation on the DynamoDB table
        dynamo_result = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('username').eq(username))
        
        default_quota = None
        body = []
        #If the user doesn't have a defined quota, and they have not made any requests yet, their quota is the default one, and their usage is 0
        if not dynamo_result['Items']:
            default_quota = get_default_quota()
            frequency = next(iter(default_quota))
            limit = default_quota[frequency]
            body.append({
                "username": username,
                "frequency": frequency,
                "limit": limit,
                "total_estimated_cost": "0.0",
            })
        else:
            #Group items by username/apikey
            grouped_items = defaultdict(list)
            for item in dynamo_result['Items']:
                # Split the sort key to get the type and key
                _, sort_key_value = item['document_type_id'].split(':')
                # Append the item to the correct group
                grouped_items[sort_key_value].append(item)

            for key, items in grouped_items.items():
                quota_summary = {}
                requests_summary_item = None
                quota_config_item = None

                for item in items:
                    if 'quota_config' in item['document_type_id']:
                        quota_config_item = item
                    if 'requests_summary' in item['document_type_id']:
                        requests_summary_item = item
                
                frequency = None
                limit = None
                if not quota_config_item:
                    if not default_quota:
                        default_quota = get_default_quota()
                    frequency = next(iter(default_quota))
                    limit = default_quota[frequency]
                else:
                    quota_map = quota_config_item["quota_map"]
                    frequency = next(iter(quota_map))
                    limit = quota_map[frequency]

                quota_summary["username"] = username
                quota_summary["frequency"] = frequency
                quota_summary["limit"] = limit

                total_estimated_cost = None
                if not requests_summary_item:
                    total_estimated_cost = "0.0"
                else:
                    total_estimated_cost = str(requests_summary_item["quota_limit_map"][frequency]["total_estimate_cost"])
                
                quota_summary["total_estimated_cost"] = total_estimated_cost

                body.append(quota_summary)

        response['body'] = json.dumps(body)
    except Exception as e:
        # Handle potential errors
            return {
                "statusCode": 500,
                "body": json.dumps({"message": str(e)})
            }

def lambda_handler(event, context):
    """
    :param event: A dict that contains request data, query string parameters, and
                  other data sent by API Gateway.
    :param context: Context around the request.
    :return: A response dict that contains an HTTP status code that indicates the
             result of handling the event.
    """
    http_method = event.get('httpMethod')
    table = boto3.resource("dynamodb").Table(QUOTA_TABLE_NAME)
    headers = event["headers"]

    query_params = event.get('queryStringParameters') or {}  # Use an empty dict as a default
    username = query_params.get('username', None)

    response = {"statusCode": 200}

    path = event['path']
    print(f'http_method: {http_method} path: {path}')
    if http_method == 'GET' and path == "/quota/summary":
        print(f'getting quota summary for user {username}')
        if not username:
            return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "query parameter 'username' is required"})
                }
        error = get_quota_summary(username, table, response)
        if error:
            return error
    elif http_method == 'GET' and path == "/quota/currentusersummary":
        authorization_header = headers["Authorization"]
        username = get_user_name(authorization_header)
        error = get_quota_summary(username, table, response)
        if error:
            return error
    elif http_method == 'GET' and path == "/quota":
        if not username:
            return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "query parameter 'username' is required"})
                }
        print(f'getting custom quota config for user {username}')
        try:
            body = {}
            dynamo_result = table.query(
                    KeyConditionExpression=Key('username').eq(username) & Key('document_type_id').eq(f"quota_config:{username}")
            )

            if dynamo_result['Items']:
                body['quota_map'] = dynamo_result['Items'][0]["quota_map"]
                body['default'] = "false"
            else:
                body['quota_map'] = get_default_quota()
                body['default'] = "true"

            response['body'] = json.dumps(body)

        except Exception as e:
            # Handle potential errors
             return {
                "statusCode": 500,
                "body": json.dumps({"message": str(e)})
            }
    elif http_method == 'POST':
        if not username:
            return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "query parameter 'username' is required"})
                }
        try:
            # Parse body to get username and api_key_name
            body = json.loads(event.get('body', '{}'))
            if not body:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "Must pass in a request body with a string key of 'weekly', and a positive float number value"})
                }
            
            if len(body) != 1:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "Currently only support a single quota type"})
                }
            
            quota_map = {}
            for key, value in body.items():
                print(f"Key: {key}, Value: {value}")
                if key != 'weekly':
                    return {
                        "statusCode": 400,
                        "body": json.dumps({"message": "Must pass in a request body with a string key of 'weekly', and a positive float number value"})
                    }
                if not can_convert_to_decimal(value):
                    return {
                        "statusCode": 400,
                        "body": json.dumps({"message": "Must pass in a request body with a string key of 'weekly', and a positive float number value"})
                    }
                quota_map[key] = str(value)

            dynamo_response = table.put_item(
                Item={
                    'username': username,
                    'document_type_id': f'quota_config:{username}',
                    'quota_map': quota_map
                }
            )

            # Return the newly created API key details
            response['body'] = json.dumps({
                "username": username,
                "quota_map": quota_map,
            })
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                response = {
                    "statusCode": 400,
                    "body": json.dumps({"message": "Key name already exists"})
                }
            else:
                response = {
                    "statusCode": 500,
                    "body": json.dumps({"message": str(e)})
                }
        except Exception as e:
            response = {
                "statusCode": 500,
                "body": json.dumps({"message": str(e)})
            }
    elif http_method == 'DELETE':
        # Handle DELETE request

        try:
            # Perform a delete operation on the DynamoDB table
            result = table.delete_item(
                Key={
                    'username': username,
                    'document_type_id': f'quota_config:{username}'
                }
            )
            # Return success message
            response['body'] = json.dumps({"message": "Record deleted successfully"})
        except Exception as e:
            response = {
                "statusCode": 500,
                "body": json.dumps({"message": str(e)})
            }
    else:
        # Method not allowed
        return {
            'statusCode': 405,
            'body': 'Method Not Allowed'
        }
    
    return response
