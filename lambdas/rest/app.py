from langchain.agents.initialize import initialize_agent
import boto3
import json
import langchain
import os
import uuid

# Local imports
# import files

DEFAULT_DATASET = str(os.environ.get("DEFAULT_DATASET", "B2B"))
DEFAULT_MAX_TOKENS = int(os.environ.get("DEFAULT_MAX_TOKENS", 4096))
DEFAULT_STOP_SEQUENCES = ["Human", "Question", "Customer", "Guru"]
DEFAULT_TEMP = float(os.environ.get("DEFAULT_TEMP", 0.2))
DEFAULT_LANGCHAIN_USE = bool(os.environ.get("DEFAULT_LANGCHAIN_USE", False))
MODEL = os.environ.get("MODEL", "anthropic.claude-v2")  # amazon.titan-tg1-large
REGION = os.environ.get("REGION", "us-west-2")

# Specify the local Bedrock installation location
session = boto3.Session()
session._loader.search_paths.extend(["/root/.aws/models"])
client = session.client("bedrock-runtime", REGION)
print("Initialized Bedrock client.")


def format_bedrock_request(prompt, temperature, max_tokens_to_sample, stop_sequences):
    bedrock_request = {
        "prompt": prompt,
        "temperature": temperature,
    }
    if "anthropic" in MODEL:
        bedrock_request["max_tokens_to_sample"] = max_tokens_to_sample
        bedrock_request["stop_sequences"] = stop_sequences
    elif "cohere" in MODEL:
        bedrock_request["stop_sequences"] = stop_sequences
    elif "ai21" in MODEL:
        print(1 + 1)
    elif "amazon" in MODEL:
        bedrock_request = {"inputText": prompt}
    return bedrock_request


def lambda_handler(event, context):
    print("event:", event)
    print("context:", context)
    # Get config from the request body.
    body = json.loads(event["body"])
    prompt = body["prompt"]
    model_kwargs = body["parameters"]
    # Set config values from the kwargs found inside the request body.
    temperature = model_kwargs.get("temperature", DEFAULT_TEMP)
    stop_sequences = model_kwargs.get("stop_sequences", DEFAULT_STOP_SEQUENCES)
    max_tokens_to_sample = model_kwargs.get("max_tokens_to_sample", DEFAULT_MAX_TOKENS)

    full_chat = f"""\n\nHuman: {prompt} \n\nAssistant:"""

    bedrock_request = format_bedrock_request(
        full_chat,
        temperature,
        max_tokens_to_sample,
        stop_sequences,
    )

    print(bedrock_request)
    payload = json.dumps(bedrock_request)
    response = client.invoke_model(
        modelId=MODEL,
        contentType="application/json",
        accept="application/json",
        body=payload,
    )

    response_body = response.get("body").read()
    response_body = json.loads(response_body.decode("utf-8"))

    print(response_body)
    return {
        "statusCode": 200,
        "body": json.dumps(response_body),
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
    }
