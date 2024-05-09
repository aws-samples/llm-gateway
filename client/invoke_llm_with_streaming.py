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

async def llm_answer_streaming(prompt):
    message = {"action": "sendmessage", "prompt": prompt}
    if thread_safe_session_state.get("chat_id"):
        print(f'found chat id in context')
        message["chat_id"] = thread_safe_session_state.get("chat_id")
    else:
        print(f'did not find chat id in context')
    socket = await websockets.connect(uri)

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
