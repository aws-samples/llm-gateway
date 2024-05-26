import boto3
import datetime
import json
import logging
import os
import requests
import uuid
import secrets
import hashlib
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

## BEGIN ENVIORNMENT VARIABLES #################################################
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
# Chat history.
API_KEY_TABLE_NAME = os.environ.get("API_KEY_TABLE_NAME", None)
COGNITO_DOMAIN_PREFIX = os.environ.get("COGNITO_DOMAIN_PREFIX")

REGION = os.environ.get("REGION")

def now():
    return datetime.datetime.now()

class Settings:
    def __init__(self, event, session):
        self.dynamodb_client = boto3.client("dynamodb")

        # Get config from the request body.
        body = json.loads(event["body"])
        self.prompt = body["prompt"]

## END NETWORK ANALYSIS ########################################################
## BEGIN WEBSOCKETS ############################################################

def get_username(authorization_header):
    user_info = get_user_info(authorization_header)
    return user_info["preferred_username"]

def get_user_info(authorization_header):
    url = f'https://{COGNITO_DOMAIN_PREFIX}.auth.{REGION}.amazoncognito.com/oauth2/userInfo'

    # Set the headers with the access token
    headers = {
        'Authorization': authorization_header
    }

    # Make the HTTP GET request to the User Info endpoint
    response = requests.get(url, headers=headers)

    # Check if the request was successful
    if response.status_code == 200:
        return response.json()  # Returns the user info as a JSON object
    else:
        return response.status_code, response.text  # Returns error status and message if not successful

def generate_api_key(key_size=32):
  """Generates a cryptographically secure API key of specified size in bytes.

  Args:
      key_size: The desired length of the API key in bytes (default: 32).

  Returns:
      A randomly generated API key as a bytes object.
  """
  # Use secrets.token_bytes for cryptographically secure random data
  random_bytes = secrets.token_bytes(key_size)

  # Convert bytes to a URL-safe base64 string (optional for readability)
  api_key = random_bytes.hex()  # Or base64.urlsafe_b64encode(random_bytes).decode('utf-8')

  return api_key

def hash_api_key(api_key_value):
    """
    Generates a SHA-256 hash of the API key value.
    """
    hasher = hashlib.sha256()
    hasher.update(api_key_value.encode('utf-8'))  # Ensure the input is encoded to bytes
    return hasher.hexdigest()


def lambda_handler(event, context):
    """
    :param event: A dict that contains request data, query string parameters, and
                  other data sent by API Gateway.
    :param context: Context around the request.
    :return: A response dict that contains an HTTP status code that indicates the
             result of handling the event.
    """
    http_method = event.get('httpMethod')
    table = boto3.resource("dynamodb").Table(API_KEY_TABLE_NAME)
    headers = event["headers"]
    print(f'headers: {headers}')
    username = ""
    if not headers or "Authorization" not in headers:
        response = {
                "statusCode": 500,
                "body": json.dumps({"message": str("Unexpected lack of authorization header.")})
            }
    else:
        authorization_header = headers["Authorization"]
        username = get_username(authorization_header)

    response = {"statusCode": 200}

    if http_method == 'GET':
        try:
            # Perform a query operation on the DynamoDB table
            result = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('username').eq(username)
            )

            # Prepare items excluding the api_key_value_hash
            if 'Items' in result:
                clean_items = [{key: item[key] for key in item if key != 'api_key_value_hash'} for item in result['Items']]
                response['body'] = json.dumps(clean_items)
            else:
                response['body'] = json.dumps([])
        
        except Exception as e:
            # Handle potential errors
            response = {
                "statusCode": 500,
                "body": json.dumps({"message": str(e)})
            }
    elif http_method == 'POST':
        try:
            # Parse body to get username and api_key_name
            body = json.loads(event.get('body', '{}'))
            api_key_name = body.get('api_key_name')
            expiration_timestamp = body.get('expiration_timestamp')

            if not api_key_name:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "api_key_name is required"})
                }

            api_key_value = generate_api_key()
            hashed_api_key_value = hash_api_key(api_key_value)

            # Insert new item into DynamoDB
            table.put_item(
                Item={
                    'username': username,
                    'api_key_name': api_key_name,
                    'api_key_value_hash': hashed_api_key_value,
                    'expiration_timestamp': expiration_timestamp
                },
                ConditionExpression='attribute_not_exists(username) AND attribute_not_exists(api_key_name)'
            )
            # Return the newly created API key details
            response['body'] = json.dumps({
                "username": username,
                "api_key_name": api_key_name,
                "api_key_value": api_key_value
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
        params = event.get('queryStringParameters', {})
        api_key_name = params.get('api_key_name')
        if not api_key_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "api_key_name parameter is required"})
            }

        try:
            # Perform a delete operation on the DynamoDB table
            result = table.delete_item(
                Key={
                    'username': username,
                    'api_key_name': api_key_name
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
