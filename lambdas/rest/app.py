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
DEFAULT_TEMP = float(os.environ.get("DEFAULT_TEMP", 0.2))
DEFAULT_LANGCHAIN_USE = bool(os.environ.get("DEFAULT_LANGCHAIN_USE", False))
REGION = os.environ.get("REGION", "us-west-2")
COUNT_TOKENS_LAMBDA = os.environ.get("COUNT_TOKENS_LAMBDA")

# Specify the local Bedrock installation location
session = boto3.Session()
session._loader.search_paths.extend(["/root/.aws/models"])
client = session.client("bedrock-runtime", REGION)
print("Initialized Bedrock client.")


def format_bedrock_request(prompt, temperature, max_tokens_to_sample,
                           stop_sequences, model):
    bedrock_request = {
        "prompt": prompt,
        "temperature": temperature,
    }
    if "anthropic" in model:
        bedrock_request["max_tokens_to_sample"] = max_tokens_to_sample
        bedrock_request["stop_sequences"] = stop_sequences
    elif "cohere" in model:
        bedrock_request["stop_sequences"] = stop_sequences
    elif "ai21" in model:
        print(1 + 1)
    elif "amazon" in model:
        bedrock_request = {"inputText": prompt}
    return bedrock_request


def collect_metrics(s):
    return {}
    raise NotImplementedError()

    return response


def lambda_handler(event, context):
    print("event:", event)
    print("context:", context)
    # Get config from the request body.
    body = json.loads(event["body"])
    prompt = body["prompt"]
    model = body["model"]
    # Set config values from the kwargs found inside the request body.
    model_kwargs = body["parameters"]
    temperature = model_kwargs.get("temperature", DEFAULT_TEMP)
    stop_sequences = model_kwargs.get("stop_sequences", [])
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
        modelId=model,
        contentType="application/json",
        accept="application/json",
        body=payload,
    )

    # Collect metrics for the input and output.
    input_metrics = collect_metrics(prompt)
    output_metrics = collect_metrics(response)
    metrics = {
        "input": input_metrics,
        "output": output_metrics,
    }

    response_body = response.get("body").read()
    response_body = json.loads(response_body.decode("utf-8"))

    print(response_body)

    return {
        "statusCode": 200,
        "body": json.dumps(response_body),
        "metrics": metrics,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
    }
