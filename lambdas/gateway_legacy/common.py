from botocore.exceptions import ClientError
from langchain_community.chat_models import BedrockChat
from langchain_openai import ChatOpenAI
from langchain_community.embeddings import BedrockEmbeddings
from langchain_community.llms import Bedrock
import boto3
import datetime
import json
import logging
import os
from langchain_core.messages import HumanMessage
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_openai import AzureChatOpenAI
import requests
import hashlib

logger = logging.getLogger()
logger.setLevel(logging.INFO)

## BEGIN ENVIORNMENT VARIABLES #################################################
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
# Chat history.
CHAT_HISTORY_TABLE = os.environ.get("CHAT_HISTORY_TABLE_NAME", None)
# Default Bedrock LLM settings.
DEFAULT_MAX_TOKENS = int(os.environ.get("DEFAULT_MAX_TOKENS", 4096))
DEFAULT_STOP_SEQUENCES = ["Human", "Question", "Customer", "Guru"]
DEFAULT_TEMP = float(os.environ.get("DEFAULT_TEMP", 0.0))
# Model selection.
EMBEDDINGS_MODEL = os.environ.get("EMBEDDINGS_MODEL")
COGNITO_DOMAIN_PREFIX = os.environ.get("COGNITO_DOMAIN_PREFIX")
## END ENVIORNMENT VARIABLES ###################################################
## BEGIN NETWORK ANALYSIS ######################################################
REGION = os.environ.get("REGION")
API_KEY_TABLE_NAME = os.environ.get("API_KEY_TABLE_NAME", None)

SALT_SECRET = os.environ.get("SALT_SECRET")

secrets_manager_client = boto3.client("secretsmanager")

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

def now():
    return datetime.datetime.now()

def get_messages_from_history(chat_history, message_type):
    if len(chat_history) == 0:
        return []
    try:
        print("Chat history:", chat_history)
        json_string = chat_history.get("Item", {}).get(message_type, {}).get("S", {})
        return json.loads(json_string)
    except:
        return []
    
def get_cache(dynamodb_client, previous_requests, node_id, prompt, invalidate_cache):
    # We are only caching the first request+response, if there is history, this is not the first request.
    if previous_requests:
        return []
    # We are caching based on the combination of prompt and node_id. If we don't have both, we can't look up.
    if not node_id or not prompt:
        return []
    # If the caller wants to invalidate the cache, we skip it, and it will be overwritten
    if invalidate_cache:
        print(
            "invalidating the cache. We will go to LLM for response and overwrite the current cache."
        )
        return []

    try:
        response = dynamodb_client.get_item(
            TableName=CHAT_HISTORY_TABLE,
            Key={
                "id": {"S": node_id + prompt},
            },
        )
        if "ResponseMetadata" in response:
            return response
        else:
            print("Failed to retrieve cached first request + response:", response)
        return []
    except Exception as e:
        print("Error retrieving cached first request + response:", str(e))
        return []

def get_chat_history(dynamodb_client, chat_id):
    try:
        response = dynamodb_client.get_item(
            TableName=CHAT_HISTORY_TABLE,
            Key={
                "id": {"S": chat_id},
            },
        )
        if "ResponseMetadata" in response:
            return response
        else:
            print("Failed to retrieve chat history:", response)
        return []
    except Exception as e:
        print("Error retrieving chat history:", str(e))
        return []
    
def post_to_history(dynamodb_client, chat_id, model, history):
    print(f'history: {history}')
    requests = []
    responses = []

    for i in range(0, len(history), 2):
        humanMessage = history[i]
        aiMessage = history[i + 1]
        requests.append(humanMessage.content)
        responses.append(aiMessage.content)

    print(f'requests: {requests}')
    print(f'responses: {responses}')

    try:
        response = dynamodb_client.put_item(
            TableName=CHAT_HISTORY_TABLE,
            Item={
                "id": {"S": chat_id},
                "model": {"S": model},
                "requests": {"S": json.dumps(requests)},
                "responses": {"S": json.dumps(responses)},
            },
        )
        if "ResponseMetadata" in response:
            print("Message saved to history!")
        else:
            print("Failed to save message to history:", response)
    except Exception as e:
        print("Error saving message to history:", str(e))

def post_to_cache(dynamodb_client, node_id, prompt, responses):
    print("responses:", responses)
    try:
        response = dynamodb_client.put_item(
            TableName=CHAT_HISTORY_TABLE,
            Item={
                "id": {"S": node_id + prompt},
                "responses": {"S": json.dumps(responses)},
            },
        )
        if "ResponseMetadata" in response:
            print("Message saved to cache!")
        else:
            print("Failed to save message to cache:", response)
    except Exception as e:
        print("Error saving message to cache:", str(e))

def append_prompt_to_history(prompt, previous_requests, previous_responses,
                             model,):
    # Reconstruct the previous conversation.
    print(f'previous_requests: {previous_requests}')
    print(f'previous_requests: {previous_responses}')
    messages = []
    for i in range(len(previous_requests)):
        request = previous_requests[i]
        print(f'request: {request}')
        response = previous_responses[i]
        print(f'response: {response}')
        messages.append(HumanMessage(content=request))
        messages.append(AIMessage(content=response))
    messages.append(HumanMessage(content=prompt))
    return messages

class Settings:
    def __init__(self, event, session):
        self.dynamodb_client = boto3.client("dynamodb")
        # Set up Bedrock client (special case -- we need to load from the environment).
        self.bedrock_runtime = session.client("bedrock-runtime")
        print("Initialized Bedrock client.")

        # Get config from the request body.
        body = json.loads(event["body"])
        self.prompt = body["prompt"]

        self.provider = body["provider"]
        self.model = body["model"]

        print("Using provider:", self.provider)
        print("Using model:", self.model)
        model_kwargs = body.get("parameters", {})

        self.node_id = model_kwargs.get("node_id", None)

        # Set config values from the kwargs found inside the request body.
        self.temperature = model_kwargs.get("temperature", DEFAULT_TEMP)
        self.max_tokens_to_sample = model_kwargs.get(
            "max_tokens_to_sample",
            DEFAULT_MAX_TOKENS,
        )
        self.stop_sequences = model_kwargs.get("stop_sequences", DEFAULT_STOP_SEQUENCES)
        self.chat_id = body.get("chat_id", now().isoformat())
        self.rag_prompt = body.get("rag_prompt", None)
        self.invalidate_cache = body.get("invalidate_cache", "false").lower() == "true"

#ToDo: Use username to look up whether user has exceeded thier ratelimit
def has_exceeded_rate_limit(user_name):
    return False

def get_llm_chat(settings: Settings):
    print(f'settings.model: {settings.model}')
    if settings.provider.lower() == "openai":
        llm_chat = ChatOpenAI(
            model=settings.model,
            temperature=0
        )
        print(f'using ChatOpenAI')
    elif settings.provider.lower() == "google":
        llm_chat = ChatGoogleGenerativeAI(model=settings.model)
        print(f'using ChatGoogleGenerativeAI')
    #(the Bedrock Claude models start with "anthropic", and the Anthropic Claude models start with "claude")
    elif settings.provider.lower() == "anthropic":
        llm_chat = ChatAnthropic(temperature=0, model_name=settings.model)
        print(f'using ChatAnthropic')
    elif settings.provider.lower() == "azure":
        llm_chat = AzureChatOpenAI(
            azure_deployment=settings.model,
        )
    elif settings.provider.lower() == "amazon":
        # Create a LangChain BedrockChat to stream the results.
        llm_chat = BedrockChat(
            model_id=settings.model,
            client=settings.bedrock_runtime,
            model_kwargs={
                # "max_tokens_to_sample": 4096,
                "temperature": 0.0,
            },
        )
        print(f'using BedrockChat')
    else:
        print("Error: Unrecognized provider")
        llm_chat = None

    return llm_chat

def handle_cache(settings: Settings, previous_requests):
    # Check if we have answered this question before for this node.
    cache_start_time = now()
    cache = get_cache(
        settings.dynamodb_client,
        previous_requests,
        settings.node_id,
        settings.prompt,
        settings.invalidate_cache,
    )
    cached_responses = get_messages_from_history(cache, "responses")
    cache_end_time = now()
    if cached_responses:
        print(
            f"Have already answered prompt {settings.prompt} for this node {settings.node_id}. Using cache."
        )
        cache_latency = cache_end_time - cache_start_time
        print("cache_latency", cache_latency)
    return cached_responses

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
    
def get_user_name(authorization_header):
    try:
        user_info = get_user_info_cognito(authorization_header)
        print(f'user_info: {user_info}')
        user_name = user_info["preferred_username"]
        return user_name
    except:
        user_name = get_user_name_api_key(authorization_header)
        return user_name
    
def extract_token(authorization_header):
    token_parts = authorization_header.split(' ')
    if token_parts[0] != 'Bearer' or len(token_parts) != 2:
        raise ValueError("Invalid Authorization token format")
    encoded_token = token_parts[1]
    return encoded_token

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
    api_key_value = extract_token(authorization_header)
    hashed_api_key_value = hash_api_key(api_key_value)
    api_key_document = query_by_api_key_hash(hashed_api_key_value)
    return api_key_document.get('username')

def get_user_info_cognito(authorization_header):
    url = f'https://{COGNITO_DOMAIN_PREFIX}.auth.{REGION}.amazoncognito.com/oauth2/userInfo'

    # Set the headers with the access token
    headers = {
        'Authorization': authorization_header
    }

    # Make the HTTP GET request to the User Info endpoint
    response = requests.get(url, headers=headers)

    # Check if the request was successful
    if response.status_code == 200:
        return response.json()  # Returns the user info as a JSON object
    else:
        return response.status_code, response.text  # Returns error status and message if not successful