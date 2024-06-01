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
import openai

# loading in environment variables
load_dotenv()


ApiUrl = os.environ["ApiUrl"]
print(f'ApiUrl: {ApiUrl}')

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

async def llm_answer_streaming(question, model, access_token):
    client = openai.AsyncOpenAI(base_url=ApiUrl, api_key=access_token)

    if thread_safe_session_state.get("chat_id"):
        chat_id = thread_safe_session_state.get("chat_id")
        # ToDo: Restore chat_id functionality to support server side history
        #message["chat_id"] = thread_safe_session_state.get("chat_id")
        print(f'found chat id {chat_id} in context')
    else:
        print(f'did not find chat id in context')

    stream = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": question}],
        max_tokens=1000,
        temperature=1,
        n=1,
        stream=True
    )
    # ToDo: Restore chat_id functionality to support server side history
    # print(f'Assigning chat id: {response_json.get("chat_id")}')
    # thread_safe_session_state.set("chat_id", response_json.get("chat_id"))
    async for chunk in stream:
        try:
            yield chunk.choices[0].delta.content if chunk.choices[0].finish_reason != "stop" else ''
        except:
            yield 'error!'
