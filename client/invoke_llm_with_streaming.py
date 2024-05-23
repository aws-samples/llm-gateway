import boto3
import json
import botocore.config
import os
from dotenv import load_dotenv
import streamlit as st
import websockets
import threading

# loading in environment variables
load_dotenv()

# configuring our CLI profile name
boto3.setup_default_session(profile_name=os.getenv('profile_name'))
# increasing the timeout period when invoking bedrock
config = botocore.config.Config(connect_timeout=120, read_timeout=120)
# instantiating the bedrock client
region = boto3.Session().region_name
bedrock = boto3.client('bedrock-runtime', region, endpoint_url=f'https://bedrock-runtime.{region}.amazonaws.com',
                       config=config)

resources_file_path = '../cdk/resources.txt'
scripts_resources_file_path = '../scripts/resources.txt'
# Initialize variables to hold the values
UserPoolID = None
UserPoolClientID = None
WebSocketURL = None
Username = None
Password = None

if os.path.exists(resources_file_path):
    # Open the file and read the contents
    with open(resources_file_path, 'r') as file:
        # Iterate over each line in the file
        for line in file:
            stripped_line = line.strip()
            if '=' in stripped_line:
                # Split the line into key and value on the '=' character
                key, value = line.strip().split('=')
                # Assign the value to the appropriate variable based on the key
                if key == 'UserPoolID':
                    UserPoolID = value
                elif key == 'UserPoolClientID':
                    UserPoolClientID = value
                elif key == 'WebSocketURL':
                    WebSocketURL = value
else:
    print(f"Error: The file {resources_file_path} does not exist")

if os.path.exists(scripts_resources_file_path):
    # Open the file and read the contents
    with open(scripts_resources_file_path, 'r') as file:
        # Iterate over each line in the file
        for line in file:
            stripped_line = line.strip()
            if '=' in stripped_line:
                # Split the line into key and value on the '=' character
                key, value = line.strip().split('=')
                # Assign the value to the appropriate variable based on the key
                if key == 'Username':
                    Username = value
                elif key == 'Password':
                    Password = value
else:
    print(f"Error: The file {scripts_resources_file_path} does not exist")

print(f'UserPoolID: {UserPoolID}')
print(f'UserPoolClientID: {UserPoolClientID}')
print(f'WebSocketURL: {WebSocketURL}')
print(f'Username: {Username}')
print(f'Password: {Password}')

class ThreadSafeSessionState:
    def __init__(self):
        self.lock = threading.Lock()
        self.session_state = {}

    def get(self, key):
        with self.lock:
            return self.session_state.get(key)

    def set(self, key, value):
        with self.lock:
            self.session_state[key] = value

thread_safe_session_state = ThreadSafeSessionState()

def authenticate_user(client_id, user_pool_id, username, password):
    client = boto3.client('cognito-idp', region_name=region)

    response = client.initiate_auth(
        ClientId=client_id,
        AuthFlow='USER_PASSWORD_AUTH',
        AuthParameters={
            'USERNAME': username,
            'PASSWORD': password
        }
    )
    return response

# Use this function to get the ID token
def get_id_token(client_id, user_pool_id, username, password):
    auth_response = authenticate_user(client_id, user_pool_id, username, password)
    #print("auth_response:", auth_response)
    id_token = auth_response['AuthenticationResult']['IdToken']
    return id_token

async def llm_answer_streaming(question, model):
    message = {"action": "sendmessage", "prompt": question, "model": model}
    if thread_safe_session_state.get("chat_id"):
        print(f'found chat id in context')
        message["chat_id"] = thread_safe_session_state.get("chat_id")
    else:
        print(f'did not find chat id in context')

    id_token = get_id_token(UserPoolClientID, UserPoolID, Username, Password)
    headers = {
        "Authorization": f"Bearer {id_token}"
    }

    #print(f'id_token: {id_token}')
    socket = await websockets.connect(f'{WebSocketURL}/prod', extra_headers=headers)

    print(f"message: {message}")
    await socket.send(json.dumps(message))
    while True:
        response = await socket.recv()
        response_json = json.loads(response)
        print(f'response_json: {response_json}')
        completion = response_json.get("completion")
        print(f'Assigning chat id: {response_json.get("chat_id")}')
        thread_safe_session_state.set("chat_id", response_json.get("chat_id"))
        if completion:
            yield completion
        if response_json.get("has_more_messages") == "false":
            break
