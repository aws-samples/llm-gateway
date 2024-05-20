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
bedrock = boto3.client('bedrock-runtime', 'us-east-1', endpoint_url='https://bedrock-runtime.us-east-1.amazonaws.com',
                       config=config)

uri = "wss://8b9ldf1092.execute-api.us-east-1.amazonaws.com/prod"

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
    client = boto3.client('cognito-idp', region_name='us-east-1')
    
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
    print("auth_response:", auth_response)
    id_token = auth_response['AuthenticationResult']['IdToken']
    return id_token

# Example usage
client_id = '1dgcu4b1dfgqq6a5jjh4g4hgjh'
user_pool_id = 'us-east-1_9MnACKCzk'
username = 'mirodrr'
password = 'Mysupersecretpassword!1'

id_token = get_id_token(client_id, user_pool_id, username, password)
print("ID Token:", id_token)


async def llm_answer_streaming(question):
    message = {"action": "sendmessage", "prompt": question}
    if thread_safe_session_state.get("chat_id"):
        print(f'found chat id in context')
        message["chat_id"] = thread_safe_session_state.get("chat_id")
    else:
        print(f'did not find chat id in context')
    socket = await websockets.connect(f'{uri}?idToken={get_id_token(client_id, user_pool_id, username, password)}')

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
