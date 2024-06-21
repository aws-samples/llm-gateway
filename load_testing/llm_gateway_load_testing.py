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
#os.environ['OPENAI_API_KEY'] = 'sk-0f22e28e1244446d95b01f8bed8729e3a4cc6075628f3b07a241f71506b039cd'

def read_resources(file_path):
    """ Read resources from the file and return UserPoolID and UserPoolClientID """
    with open(file_path, 'r', encoding="utf-8") as file:
        content = file.read()
    
    resources = {}
    for line in content.splitlines():
        key, value = line.split('=')
        resources[key.strip()] = value.strip()
        
    return resources['UserPoolID'], resources['UserPoolClientID']

def create_cognito_user(user_pool_id, username, password):
    """ Create a Cognito user with the specified username and password """
    # Initialize Cognito Identity Provider client
    client = boto3.client('cognito-idp')

    try:
        # Create user with temporary password
        response = client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=username,
            TemporaryPassword=password,
            MessageAction='SUPPRESS',  # Suppresses the email
        )
        
        # Set user password permanently and mark it as not requiring change on first login
        client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=username,
            Password=password,
            Permanent=True
        )

        return response
    except Exception as e:
        print(f"An error occurred: {e}")

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

async def measure_latency(prompt, method, name):
    n_runs = 10
    total_time = 0
    total_runs = 0
    for _ in range(n_runs):
        start_time = time.perf_counter()
        await method(prompt)
        end_time = time.perf_counter()
        total_time += (end_time - start_time)
        total_runs += 1

    average_latency = total_time / n_runs
    #print(f"{name}: Average latency over {n_runs} runs: {average_latency:.6f} seconds. Total runs {total_runs}")



def get_jwt_token(client_id, client_secret, username, password):
    secret_hash = base64.b64encode(hmac.new(bytes(client_secret, 'utf-8'), bytes(
    username + client_id, 'utf-8'), digestmod=hashlib.sha256).digest()).decode()
    client = boto3.client('cognito-idp')

    try:
        # Setting up the auth flow
        auth_params = {
            'USERNAME': username,
            'PASSWORD': password,
            "SECRET_HASH": secret_hash
        }

        # Initiate the authentication request
        response = client.initiate_auth(
            #UserPoolId=user_pool_id,
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters=auth_params
        )

        # Access token
        access_token = response['AuthenticationResult']['AccessToken']

        return access_token

    except client.exceptions.NotAuthorizedException as e:
        print(f"The username or password is incorrect: {e}")
    except client.exceptions.UserNotFoundException:
        print("The user does not exist.")
    except NoCredentialsError:
        print("Credentials are not available.")
    except Exception as e:
        print(f"An error occurred: {e}")

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

def create_api_key(access_token):
    headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
    
    body = {'api_key_name': "myapikey"}
    post_response = requests.post(ApiKeyURL, headers=headers, data=json.dumps(body), timeout=60)
    if post_response.status_code == 200:
        api_key_value = post_response.json().get("api_key_value", "")
        return api_key_value
    else:
        response_json = post_response.json()
        message = response_json.get("message")
        print('Failed to create API key: HTTP status code ' + str(post_response.status_code) + ' Error: ' + str(message))

user_pool_id, client_id = read_resources("../cdk/resources.txt")
client_secret = "1jb1gnge9v3c0i479jov3vv2h3qvpkq8a7rl39uuu6qs20gkbhhp"
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
                # Process the response if needed
                #print(response_data)
                #print(response_data['choices'][0]['message']['content'])
                #print("Request successful, processing response")
                response.success()

            else:
                response.failure(f"Failed with status code {response.status_code}")

    # @task
    # def run_streaming(self):
    #     def llm_answer_streaming(question, model):
    #         client = openai.OpenAI(
    #             api_key=self.api_key
    #         )

    #         response = client.chat.completions.create(
    #             model=model,
    #             messages=[{"role": "user", "content": question}],
    #             max_tokens=1000,
    #             temperature=1,
    #             n=1,
    #             stream=False
    #         )
    #         # print(f'response: {response}')
    #         # print(f'response.choices: {response.choices}')
    #         # print(f'response.choices[0]: {response.choices[0]}')
    #         # print(f'response.choices[0].message: {response.choices[0].message}')
    #         # print(f'response.choices[0].message.content: {response.choices[0].message.content}')
    #         try:
    #             # Retrieve the full response immediately since streaming is not enabled
    #             return response.choices[0].message.content
    #         except:
    #             return 'error!'

    #     completion = llm_answer_streaming("How does quantum computing work?", "anthropic.claude-3-haiku-20240307-v1:0")
    #     print(completion)  # Handle the completion as needed

    def on_start(self):
        self.api_key = self.generate_api_key()

    def generate_api_key(self):
        # Generate or fetch an API key
        username = generate_guid()
        password = generate_guid()
        print(f'creating cognito user: user_pool_id: {user_pool_id} username: {username} password: {password}')
        create_cognito_user(user_pool_id, username, password)
        print(f'creating cognito token: client_id: {client_id}')
        token = get_jwt_token(client_id, client_secret, username, password)
        print(f'created cognito token: token: {token}')
        api_key = create_api_key(token)
        print(f'created api key: {api_key}')

        return api_key

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    if exception:
        print(f"Request FAILED: {exception}")
    else:
        print(f"Request successful: {name}, Response time: {response_time} ms")

# events.request_failure.add_listener(on_request_failure)
# events.request_success.add_listener(on_request_success)

#asyncio.run(measure_latency("Tell me 5 cool facts", bedrock_streaming, "BEDROCK"))
#asyncio.run(measure_latency("Tell me 5 cool facts", run_streaming, "LLMGATEWAY"))

