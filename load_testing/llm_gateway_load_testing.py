import os
import openai
import time
import boto3
from locust import HttpUser, task, between, events
import uuid
from botocore.exceptions import NoCredentialsError
import requests
import json
import random
import hmac
import hashlib
import base64

llm_gateway_url = "https://llmgatewayapi2.mirodrr.people.aws.dev"
llm_gateway_llm_url = f'{llm_gateway_url}/api/v1'
ApiKeyURL = llm_gateway_url + "/apikey"
os.environ['OPENAI_BASE_URL'] = llm_gateway_llm_url

def read_resources(file_path):
    """ Read resources from the file and return UserPoolID and UserPoolClientID """
    with open(file_path, 'r', encoding="utf-8") as file:
        content = file.read()
    
    resources = {}
    for line in content.splitlines():
        key, value = line.split('=')
        resources[key.strip()] = value.strip()
        
    return resources['UserPoolID'], resources['UserPoolClientID']

async def llm_answer_streaming(question, model):
    client = openai.AsyncOpenAI()

    stream = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": question}],
        max_tokens=1000,
        temperature=1,
        n=1,
        stream=True
    )
    async for chunk in stream:
        try:
            yield chunk.choices[0].delta.content if chunk.choices[0].finish_reason != "stop" else ''
        except:
            yield 'error!'

async def run_streaming(prompt):
    async for completion in llm_answer_streaming(prompt, "anthropic.claude-3-haiku-20240307-v1:0"):
        print(completion, end="")  # Handle the completion however you need

user_pool_id, client_id = read_resources("../cdk/resources.txt")
with open('config.json', 'r') as file:
    data = json.load(file)

client_secret = data['client_secret']

with open('api_keys.txt', 'r') as file:
    api_keys = file.read().splitlines()

class OpenAIUser(HttpUser):
    wait_time = between(1, 2)
    host = llm_gateway_llm_url + "/chat/completions"  # Set the base host URL here

    @task
    def run_streaming(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "messages": [{"role": "user", "content": "How does quantum computing work?"}],
            "max_tokens": 1000,
            "temperature": 1,
            "n": 1,
            "stream": False
        }

        with self.client.request("POST", url=self.host, json=body, headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response_data = response.json()
                response.success()

            else:
                response.failure(f"Failed with status code {response.status_code}")

    def on_start(self):
        self.api_key = api_keys.pop()

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    if exception:
        print(f"Request FAILED: {exception}")
    else:
        print(f"Request successful: {name}, Response time: {response_time} ms")
