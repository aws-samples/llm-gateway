import boto3
from botocore.exceptions import NoCredentialsError
import requests
import json
import hmac
import hashlib
import base64
import time

def read_llmgateway_url(file_path):
    """ Read resources from the file and return UserPoolID and UserPoolClientID """
    with open(file_path, 'r', encoding="utf-8") as file:
        content = file.read()
    
    resources = {}
    for line in content.splitlines():
        key, value = line.split('=')
        resources[key.strip()] = value.strip()
        
    return resources['LLM_GATEWAY_DOMAIN_NAME'].replace('"', '')

llm_gateway_url = f"https://{read_llmgateway_url("../cdk/.env")}"
ApiKeyURL = llm_gateway_url + "/apikey"

def create_api_key(access_token):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    body = {'api_key_name': "myapikey"}
    max_retries = 5
    retry_delay = 1  # Start with 1 second

    for attempt in range(max_retries):
        try:
            post_response = requests.post(ApiKeyURL, headers=headers, json=body, timeout=60)
            if post_response.status_code == 200:
                return post_response.json().get("api_key_value", "")
            else:
                print(f'Failed to create API key: HTTP {post_response.status_code} Error: {post_response.json().get("message", "")}')
        except requests.exceptions.RequestException as e:
            print(f'Retry {attempt + 1}/{max_retries}. Error: {e}')
        
        time.sleep(retry_delay)
        retry_delay *= 2  # Exponential backoff

    raise Exception('API Key creation failed after maximum retries')

def get_jwt_token(client_id, client_secret, username, password):
    secret_hash = base64.b64encode(hmac.new(bytes(client_secret, 'utf-8'), bytes(username + client_id, 'utf-8'), digestmod=hashlib.sha256).digest()).decode()
    client = boto3.client('cognito-idp')
    max_retries = 5
    retry_delay = 1  # Start with 1 second

    for attempt in range(max_retries):
        try:
            auth_params = {
                'USERNAME': username,
                'PASSWORD': password,
                "SECRET_HASH": secret_hash
            }
            response = client.initiate_auth(
                ClientId=client_id,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters=auth_params
            )
            return response['AuthenticationResult']['AccessToken']
        except (client.exceptions.NotAuthorizedException, client.exceptions.UserNotFoundException) as e:
            print(f'Retry {attempt + 1}/{max_retries}. Error: {e}')
        except Exception as e:
            print(f'Retry {attempt + 1}/{max_retries}. Unexpected error: {e}')
        
        time.sleep(retry_delay)
        retry_delay *= 2  # Exponential backoff

    raise Exception('Failed to get JWT token after maximum retries')

def read_cognito_info(file_path):
    """ Read resources from the file and return UserPoolID and UserPoolClientID """
    with open(file_path, 'r', encoding="utf-8") as file:
        content = file.read()
    
    resources = {}
    for line in content.splitlines():
        key, value = line.split('=')
        resources[key.strip()] = value.strip()
        
    return resources['UserPoolID'], resources['UserPoolClientID']

if __name__ == "__main__":
    with open('config.json', 'r') as file:
        data = json.load(file)

    client_secret = data['client_secret']
    user_pool_id, client_id = read_cognito_info("../cdk/resources.txt")
    api_keys = []

    with open('users.txt', 'r') as file:
        usernames = file.readlines()
    
    for username in usernames:
        username = username.strip()  # Remove any newline characters and spaces
        try:
            token = get_jwt_token(client_id, client_secret, username, username)  # Username is the same as password
            api_key = create_api_key(token)
            api_keys.append(api_key)
            print(f'Username: {username}, API Key: {api_key}')
        except Exception as e:
            print(f'Failed to process user {username}: {e}')

    with open('api_keys.txt', 'w') as file:
        for key in api_keys:
            file.write(key + '\n')




