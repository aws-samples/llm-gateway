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
MODEL_ACCESS_TABLE_NAME = os.environ.get("MODEL_ACCESS_TABLE_NAME", None)
DEFAULT_MODEL_ACCESS_PARAMETER_NAME = os.environ.get("DEFAULT_MODEL_ACCESS_PARAMETER_NAME")
COGNITO_DOMAIN_PREFIX = os.environ.get("COGNITO_DOMAIN_PREFIX")
ssm_client = boto3.client("ssm")

REGION = os.environ.get("REGION")

class Settings:
    def __init__(self, event, session):
        self.dynamodb_client = boto3.client("dynamodb")
        # Get config from the request body.
        body = json.loads(event["body"])
        self.prompt = body["prompt"]

def get_default_model_access():
    response = ssm_client.get_parameter(Name=DEFAULT_MODEL_ACCESS_PARAMETER_NAME, WithDecryption=True)
    parameter_value = response['Parameter']['Value']
    default_model_access_config_dict = json.loads(parameter_value)
    return default_model_access_config_dict

def get_user_name(authorization_header):
    user_info = get_user_info_cognito(authorization_header)
    print(f'user_info: {user_info}')
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

def get_user_model_access_map(table, username, response):
    print(f'getting custom quota config for user {username}')
    try:
        body = {}
        dynamo_result = table.query(
                KeyConditionExpression=Key('username').eq(username)
        )

        if dynamo_result['Items']:
            body = dynamo_result['Items'][0]["model_access_map"]
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
    table = boto3.resource("dynamodb").Table(MODEL_ACCESS_TABLE_NAME)
    headers = event["headers"]
    print(f'headers: {headers}')

    query_params = event.get('queryStringParameters') or {}  # Use an empty dict as a default
    username = query_params.get('username', None)

    response = {"statusCode": 200}

    path = event['path']
    print(f'http_method: {http_method} path: {path}')
    
    if http_method == 'GET' and path == "/modelaccess":
        if not username:
            return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "query parameter 'username' is required"})
                }
        error = get_user_model_access_map(table, username, response)
        if error:
            return error
    elif http_method == 'GET' and path == "/modelaccess/summary":
        if not username:
            return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "query parameter 'username' is required"})
                }
        error = get_user_model_access_map(table, username, response)
        if error:
            print(f'error: {error}')
            return error
        print(f"response['body']: {response['body']}")
        if response['body'] == "{}":
            print(f"getting default model access")
            response['body'] = json.dumps(get_default_model_access())
            print(f"getting default model access")
    elif http_method == 'GET' and path == "/modelaccess/currentusersummary":
        authorization_header = headers["Authorization"]
        username = get_user_name(authorization_header)
        error = get_user_model_access_map(table, username, response)
        if error:
            return error
        if response['body'] == "{}":
            response['body'] = json.dumps(get_default_model_access())
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
                    "body": json.dumps({"message": "Must pass in a request body with a string key of 'model_access_list', and comma separated string of model ids"})
                }
            
            if len(body) != 1:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "Only the single key 'model_access_list' is supported"})
                }
            
            model_access_map = {}
            for key, value in body.items():
                print(f"Key: {key}, Value: {value}")
                if key != 'model_access_list':
                    return {
                        "statusCode": 400,
                        "body": json.dumps({"message": "Must pass in a request body with a string key of 'model_access_list', and comma separated string of model ids"})
                    }
                model_access_map[key] = str(value)

            dynamo_response = table.put_item(
                Item={
                    'username': username,
                    'model_access_map': model_access_map
                }
            )

            # Return the newly created API key details
            response['body'] = json.dumps({
                "username": username,
                "model_access_map": model_access_map,
            })
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
