import os
import logging
from jose import jwk, jwt
from jose.utils import base64url_decode
import time
import urllib.request
import json
import requests
import hashlib
import boto3
from cachetools import TTLCache

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cache = TTLCache(maxsize=10000, ttl=300)

# Configuration from environment variables
USER_POOL_ID = os.environ['USER_POOL_ID']
APP_CLIENT_ID = os.environ['APP_CLIENT_ID']
ADMIN_LIST = [item.strip() for item in os.environ.get('ADMIN_LIST', '').split(',')]
COGNITO_DOMAIN_PREFIX = os.environ['COGNITO_DOMAIN_PREFIX']
REGION = os.environ['REGION']
NON_ADMIN_ENDPOINTS = [item.strip() for item in os.environ.get('NON_ADMIN_ENDPOINTS', '').split(',')]
API_KEY_EXCLUDED_ENDPOINTS = [item.strip() for item in os.environ.get('API_KEY_EXCLUDED_ENDPOINTS', '').split(',')]
SALT_SECRET = os.environ.get("SALT_SECRET")
API_KEY_TABLE_NAME = os.environ.get("API_KEY_TABLE_NAME", None)

authorized_cache_value = "authorized"
unauthorized_cache_value = "unauthorized"

secrets_manager_client = boto3.client("secretsmanager")

print("AdminList:", ADMIN_LIST)
print("CognitoDomainPrefix:", COGNITO_DOMAIN_PREFIX)
print("Region:", REGION)

def add_to_cache(key, value):
    cache[key] = value

def get_from_cache(key):
    return cache.get(key, None)

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

def get_user_name(authorization_header, claims):
    if claims['scope'] == "aws.cognito.signin.user.admin":
        print(f'Scope is "aws.cognito.signin.user.admin". Getting username directly from token')
        return claims['username']
    user_info = get_user_info_cognito(authorization_header, claims)
    print(f'user_info: {user_info}')
    user_name = user_info["preferred_username"] if 'preferred_username' in user_info  else user_info["username"]
    print(f'user_name: {user_name}')
    return user_name

def get_user_info_cognito(authorization_header):
    url = f'https://{COGNITO_DOMAIN_PREFIX}.auth.{REGION}.amazoncognito.com/oauth2/userInfo'

    # Set the headers with the access token
    headers = {
        'Authorization': "Bearer " + authorization_header
    }

    # Make the HTTP GET request to the User Info endpoint
    response = requests.get(url, headers=headers, timeout=60)
    print(f'response: {response}. response.status_code: {response.status_code}')
    # Check if the request was successful
    if response.status_code == 200:
        print(f'response.json(): {response.json()}')
        return response.json()  # Returns the user info as a JSON object
    else:
        print(f'response.text: {response.text}')

        return response.status_code, response.text  # Returns error status and message if not successful

def validateJWT(token, app_client_id, keys):
    # get the kid from the headers prior to verification
    headers = jwt.get_unverified_headers(token)
    kid = headers['kid']
    # search for the kid in the downloaded public keys
    key_index = -1
    for i in range(len(keys)):
        if kid == keys[i]['kid']:
            key_index = i
            break
    if key_index == -1:
        logger.info('Public key not found in jwks.json')
        return False
    # construct the public key
    public_key = jwk.construct(keys[key_index])
    # get the last two sections of the token,
    # message and signature (encoded in base64)
    message, encoded_signature = str(token).rsplit('.', 1)
    # decode the signature
    decoded_signature = base64url_decode(encoded_signature.encode('utf-8'))
    # verify the signature
    if not public_key.verify(message.encode("utf8"), decoded_signature):
        logger.info('Signature verification failed')
        return False
    logger.info('Signature successfully verified')
    # since we passed the verification, we can now safely
    # use the unverified claims
    claims = jwt.get_unverified_claims(token)
    print(f'claims: {claims}')
    # additionally we can verify the token expiration
    if time.time() > claims['exp']:
        logger.info('Token is expired')
        return False
    # and the Audience  (use claims['client_id'] if verifying an access token)
    if claims['client_id'] != app_client_id:
        logger.info('Token was not issued for this audience')
        return False
    # now we can use the claims
    logger.info(claims)
    return claims

def query_by_api_key_hash(api_key_hash):
    """
    Query DynamoDB by api_key_value_hash using the secondary index and extract specific attributes.

    Args:
        api_key_hash (str): The hash value of the API key to search for.

    Returns:
        dict: A dictionary containing the username and api_key_name if found; otherwise, None.
    """
    # Initialize a DynamoDB resource. Make sure AWS credentials and region are configured.
    dynamodb = boto3.resource('dynamodb')

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
    username = api_key_document.get('username')
    if username:
        return {
            "sub": username,
            "username": username
        }
    else:
        return None

def unauthorized_response():
    return (None, {
                    "statusCode": 403,
                    "body": json.dumps({"message": "Unauthorized"})
    })

def authorized_response(user_name):
    return (user_name, None)

def get_cached_authorization(token, current_method):
    get_from_cache(token+current_method)

def cache_authorized(token, current_method, user_name):
    add_to_cache(token+current_method, authorized_cache_value + ":" + user_name)

def cache_unauthorized(token, current_method):
    add_to_cache(token+current_method, unauthorized_cache_value)

def auth_handler(event, current_method):
    try:
        headers = event["headers"]
        authorization_header = headers["authorization"]
        #get JWT token after Bearer from authorization
        token = authorization_header.split(" ")
        if (token[0] != 'Bearer'):
            raise Exception('authorization header should have a format Bearer <JWT> Token')
        bearer_token = token[1]

        cached_auth_response = get_cached_authorization(bearer_token, current_method)
        if cached_auth_response:
            logger.info(f'Cached response value for passed in token: {cached_auth_response}')
            if cached_auth_response.startswith(authorized_cache_value):
                user_name = authorized_cache_value.split(":")[1]
                return authorized_response(user_name)
            elif cached_auth_response.startswith(unauthorized_cache_value):
                return unauthorized_response()
            else:
                logger.error("unexpected cached auth value.")
                return unauthorized_response()


        keys_url = 'https://cognito-idp.{}.amazonaws.com/{}/.well-known/jwks.json'.format(REGION, USER_POOL_ID)
        with urllib.request.urlopen(keys_url) as f:
            response = f.read()
        keys = json.loads(response.decode('utf-8'))['keys']
        
        is_api_key = False
        #authenticate against cognito user pool using the key
        if bearer_token.startswith("sk-"):
            is_api_key = True
            response = get_user_name_api_key(bearer_token)
            if not response:
                cache_unauthorized(bearer_token, current_method)
                return unauthorized_response()
            user_name = response['username']
        else:
            #JWT
            response = validateJWT(bearer_token, APP_CLIENT_ID, keys)
            #get authenticated claims
            if not response:
                cache_unauthorized(bearer_token, current_method)
                return unauthorized_response()
            print(f'getting username with bearer_token: {bearer_token}')
            user_name = get_user_name(bearer_token, response)

        logger.info(response)

        if is_api_key and current_method in API_KEY_EXCLUDED_ENDPOINTS:
            logger.info(f"Access denied for user {user_name} using his api key")
            cache_unauthorized(bearer_token, current_method)
            return unauthorized_response()
        elif user_name in ADMIN_LIST:
            logger.info(f"Access granted for user admin {user_name}")
            cache_authorized(bearer_token, current_method, user_name)
            return authorized_response(user_name)
        elif current_method in NON_ADMIN_ENDPOINTS:
            logger.info(f"Access granted for user developer {user_name}")
            cache_authorized(bearer_token, current_method, user_name)
            return authorized_response(user_name)
        else:
            logger.info(f"Access denied for user developer {user_name}")
            cache_unauthorized(bearer_token, current_method)
            return unauthorized_response()
    except Exception as e:
        logger.error(f"Failed to authorize with error {e}")
        return (None, {
                "statusCode": 403,
                "body": json.dumps({"message": "Access Denied."})
            })