import os
from typing import Annotated
import boto3
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json
import os
import requests
import hashlib
import botocore
from cachetools import TTLCache
import traceback

## BEGIN ENVIORNMENT VARIABLES #################################################
COGNITO_DOMAIN_PREFIX = os.environ.get("COGNITO_DOMAIN_PREFIX")
REGION = os.environ.get("REGION")
API_KEY_TABLE_NAME = os.environ.get("API_KEY_TABLE_NAME", None)
SALT_SECRET = os.environ.get("SALT_SECRET")

cache = TTLCache(maxsize=10000, ttl=1200)
api_key_name_cache = TTLCache(maxsize=10000, ttl=1200)

authorized_cache_value = "authorized"
unauthorized_cache_value = "unauthorized"

security = HTTPBearer()
secrets_manager_client = boto3.client("secretsmanager")

def add_to_api_key_cache(key, value):
    cache[key] = value

def get_from_api_key_cache(key):
    return cache.get(key, None)

def add_to_cache(key, value):
    cache[key] = value

def get_from_cache(key):
    return cache.get(key, None)

def unauthorized_response():
    return (None, {
                    "statusCode": 403,
                    "body": json.dumps({"message": "Unauthorized"})
    })

def authorized_response(user_name):
    return (user_name, None)

def get_cached_authorization(token, current_method):
    return get_from_cache(token+current_method)

def cache_authorized(token, current_method, user_name):
    add_to_cache(token+current_method, authorized_cache_value + ":" + user_name)

def cache_unauthorized(token, current_method):
    add_to_cache(token+current_method, unauthorized_cache_value)

def api_key_auth(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    current_method
):
    #print(f'current_method: {current_method}')
    bearer_token = credentials.credentials
    cached_auth_response = get_cached_authorization(bearer_token, current_method)
    if cached_auth_response:
        #print(f'auth cache hit')
        if cached_auth_response.startswith(authorized_cache_value):
            user_name = cached_auth_response.split(":")[1]
            return authorized_response(user_name)
        elif cached_auth_response.startswith(unauthorized_cache_value):
            return unauthorized_response()
        else:
            return unauthorized_response()

    #print(f'not using the cache')
    try:
        if bearer_token.startswith("sk-"):
            user_name = get_user_name_api_key(bearer_token)
        else:
            user_name = get_user_name(bearer_token)
        if not user_name:
            cache_unauthorized(bearer_token, current_method)
            return unauthorized_response()
        #print(f'Found user_name {user_name}. Access granted.')
        cache_authorized(bearer_token, current_method, user_name)
        return authorized_response(user_name)
    except Exception as e:
        print(f'Error when trying to authenticate: {e}')
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key or JWT Cognito Access Token"
        )

def get_salt():
    try:
        get_secret_value_response = secrets_manager_client.get_secret_value(
            SecretId=SALT_SECRET
        )
    except Exception as e:
        print(f"Unable to retrieve secret: {e}")
        return None

    # Decode the JSON string and return
    if 'SecretString' in get_secret_value_response:
        secret = get_secret_value_response['SecretString']
        secret_json = json.loads(secret)
        return secret_json['salt']
    
SALT = get_salt()

#ToDo: Use username to look up whether user has exceeded thier ratelimit
def has_exceeded_rate_limit(user_name):
    return False

def query_by_api_key_hash(api_key_hash):
    """
    Query DynamoDB by api_key_value_hash using the secondary index and extract specific attributes.

    Args:
        api_key_hash (str): The hash value of the API key to search for.

    Returns:
        dict: A dictionary containing the username and api_key_name if found; otherwise, None.
    """
    client_config = botocore.config.Config(
            max_pool_connections=50,
        )
    # Initialize a DynamoDB resource. Make sure AWS credentials and region are configured.
    dynamodb = boto3.resource('dynamodb', config=client_config)

    # Access the DynamoDB table
    table = dynamodb.Table(API_KEY_TABLE_NAME)

    # Perform the query using the secondary index
    response = table.query(
        IndexName='ApiKeyValueHashIndex',  # The name of the secondary index
        KeyConditionExpression='api_key_value_hash = :hash_value',
        ExpressionAttributeValues={
            ':hash_value': api_key_hash
        }
    )

    # Extract the first item from the result, if any
    items = response.get('Items', [])
    if items:
        item = items[0]
        return item
    else:
        return None
    
def get_user_name(authorization_header):
    user_info = get_user_info_cognito(authorization_header)
    if user_info:
        user_name = user_info["preferred_username"] if 'preferred_username' in user_info else user_info.get("username")
        return user_name
    return None

def hash_api_key(api_key_value):
    """
    Generates a SHA-256 hash of the API key value, using a salt.
    
    Args:
    api_key_value (str): The API key to hash.
    
    Returns:
    str: The hex digest of the hash.
    """
    hasher = hashlib.sha256()
    # Combine the salt and the API key value. You can also hash the salt first if needed.
    salted_input = SALT + api_key_value  # or use f"{salt}{api_key_value}"
    hasher.update(salted_input.encode('utf-8'))  # Ensure the input is encoded to bytes
    return hasher.hexdigest()

def get_user_name_api_key(authorization_header):
    hashed_api_key_value = hash_api_key(authorization_header)
    api_key_document = query_by_api_key_hash(hashed_api_key_value)
    return api_key_document.get('username')

def get_api_key_name(api_key):
    hashed_api_key_value = hash_api_key(api_key)
    cached_api_key_name = get_from_api_key_cache(hashed_api_key_value)
    if cached_api_key_name:
        return cached_api_key_name
    
    api_key_document = query_by_api_key_hash(hashed_api_key_value)
    api_key_name = api_key_document.get('api_key_name')
    add_to_api_key_cache(hashed_api_key_value, api_key_name)
    return api_key_name

def get_user_info_cognito(authorization_header):
    url = f'https://{COGNITO_DOMAIN_PREFIX}.auth.{REGION}.amazoncognito.com/oauth2/userInfo'

    # Set the headers with the access token
    headers = {
        'Authorization': "Bearer " + authorization_header
    }

    # Make the HTTP GET request to the User Info endpoint
    response = requests.get(url, headers=headers, timeout=60)

    # Check if the request was successful
    if response.status_code == 200:
        return response.json()  # Returns the user info as a JSON object
    else:
        print(f'response: {response}')
        return None