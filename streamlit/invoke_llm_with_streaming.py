import boto3
import json
import botocore.config
import os
from dotenv import load_dotenv
import streamlit as st
import websockets
import threading
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session
from urllib.parse import urlparse, urlunparse

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

WebSocketURL = os.environ["WebSocketURL"]
print(f'WebSocketURL: {WebSocketURL}')

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
    def delete(self, key):
        with self.lock:
            del self.session_state[key]

thread_safe_session_state = ThreadSafeSessionState()

async def llm_answer_streaming(question, provider, model, access_token):
    message = {"action": "sendmessage", "prompt": question, "provider": provider, "model": model}

    if thread_safe_session_state.get("chat_id"):
        print(f'found chat id in context')
        message["chat_id"] = thread_safe_session_state.get("chat_id")
    else:
        print(f'did not find chat id in context')

    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    print(f'websocket headers: {headers}')
    async with websockets.connect(f'{WebSocketURL}/prod', extra_headers=headers) as websocket:
        print(f"message: {message}")
        await websocket.send(json.dumps(message))
        while True:
            response = await websocket.recv()
            response_json = json.loads(response)
            print(f'response_json: {response_json}')
            completion = response_json.get("completion")
            print(f'Assigning chat id: {response_json.get("chat_id")}')
            thread_safe_session_state.set("chat_id", response_json.get("chat_id"))
            if completion:
                yield completion
            if response_json.get("has_more_messages") == "false":
                break