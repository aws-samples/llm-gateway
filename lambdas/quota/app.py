import boto3
import datetime
import json
import logging
import os
from botocore.exceptions import ClientError
from decimal import Decimal, DecimalException

logger = logging.getLogger()
logger.setLevel(logging.INFO)

## BEGIN ENVIORNMENT VARIABLES #################################################
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
# Chat history.
QUOTA_TABLE_NAME = os.environ.get("QUOTA_TABLE_NAME", None)

REGION = os.environ.get("REGION")

def now():
    return datetime.datetime.now()

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
    print(f'headers: {headers}')

    query_params = event.get('queryStringParameters') or {}  # Use an empty dict as a default
    username = query_params.get('username', None)

    if not username:
        return {
                "statusCode": 400,
                "body": json.dumps({"message": "query parameter 'username' is required"})
            }

    response = {"statusCode": 200}

    if http_method == 'GET':
        document_type = query_params.get('document_type', "quota_config")
        if document_type != "quota_config" and document_type != "requests_summary":
            return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "query parameter 'requests_summary' must be either 'quota_config' or 'requests_summary'"})
                }

        try:
            # Perform a query operation on the DynamoDB table
            result = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('username_document_type').eq(f'{username}:{document_type}') & boto3.dynamodb.conditions.Key('id').eq(username)
            )
            body = {}
            if result["Items"]:
                body = result["Items"][0] 

            response['body'] = json.dumps(body)
        except Exception as e:
            # Handle potential errors
             return {
                "statusCode": 500,
                "body": json.dumps({"message": str(e)})
            }
    elif http_method == 'POST':
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
                    'username_document_type': f'{username}:quota_config',
                    'id': username,
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
                    'username_document_type': f'{username}:quota_config',
                    'id': username
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
