import boto3
import uuid
import random
import json
import time
import sys

client = boto3.client('cognito-idp')


def generate_guid():
    guid = str(uuid.uuid4())
    
    # Initial random conversion to mixed case
    mixed_case_guid = ''.join(char.upper() if random.random() > 0.5 else char for char in guid)
    
    # Check if there's at least one uppercase and one lowercase letter
    if not any(char.isupper() for char in mixed_case_guid):
        # Convert a random lowercase letter to uppercase
        chars = list(mixed_case_guid)
        lower_indices = [i for i, char in enumerate(chars) if char.islower()]
        if lower_indices:
            chars[random.choice(lower_indices)] = chars[random.choice(lower_indices)].upper()
        mixed_case_guid = ''.join(chars)

    if not any(char.islower() for char in mixed_case_guid):
        # Convert a random uppercase letter to lowercase
        chars = list(mixed_case_guid)
        upper_indices = [i for i, char in enumerate(chars) if char.isupper()]
        if upper_indices:
            chars[random.choice(upper_indices)] = chars[random.choice(upper_indices)].lower()
        mixed_case_guid = ''.join(chars)

    return mixed_case_guid

def create_cognito_user(user_pool_id, username, password, retries=0):
    try:
        response = client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=username,
            TemporaryPassword=password,
            MessageAction='SUPPRESS'
        )
        return response
    except Exception as e:
        if retries < 3:  # Retry up to 3 times
            time.sleep(2 ** retries)  # Exponential backoff
            return create_cognito_user(user_pool_id, username, password, retries + 1)
        else:
            print(f"Failed to create user {username} after {retries} retries. Error: {e}")

def set_cognito_user_password(user_pool_id, username, password, retries=0):
    try:
        client.admin_set_user_password(
                UserPoolId=user_pool_id,
                Username=username,
                Password=password,
                Permanent=True
            )
    except Exception as e:
        if retries < 3:  # Retry up to 3 times
            time.sleep(2 ** retries)  # Exponential backoff
            return set_cognito_user_password(user_pool_id, username, password, retries + 1)
        else:
            print(f"Failed to reset password for {username} after {retries} retries. Error: {e}")

def read_resources(file_path):
    """ Read resources from the file and return UserPoolID and UserPoolClientID """
    with open(file_path, 'r', encoding="utf-8") as file:
        content = file.read()
    
    resources = {}
    for line in content.splitlines():
        key, value = line.split('=')
        resources[key.strip()] = value.strip()
        
    return resources['UserPoolID'], resources['UserPoolClientID']
def create_multiple_users(user_pool_id, count):
    with open('users.txt', 'w') as users_file:
        for _ in range(count):
            username = generate_guid()
            password = username
            create_cognito_user(user_pool_id, username, password)
            set_cognito_user_password(user_pool_id, username, password)
            users_file.write(username + '\n')

if __name__ == "__main__":
    user_pool_id, client_id = read_resources("../cdk/resources.txt")
    num_users = int(sys.argv[1])
    create_multiple_users(user_pool_id, num_users)
