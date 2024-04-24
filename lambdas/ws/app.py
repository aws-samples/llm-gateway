from botocore.exceptions import ClientError
from langchain_community.chat_models import BedrockChat
from langchain_openai import ChatOpenAI
from langchain_community.embeddings import BedrockEmbeddings
from langchain_community.llms import Bedrock
from langchain_community.vectorstores import OpenSearchVectorSearch
from multiprocessing import Process, Pipe
from opensearchpy import RequestsHttpConnection, AWSV4SignerAuth
from sqlalchemy import create_engine
import boto3
import datetime
import json
import logging
import os
import pandas as pd

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
MODEL = os.environ.get("MODEL", "anthropic.claude-v2")
API_KEY = os.environ.get("API_KEY", "")
## END ENVIORNMENT VARIABLES ###################################################
## BEGIN NETWORK ANALYSIS ######################################################


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


def post_to_history(dynamodb_client, chat_id, model, requests, responses):
    print("requests:", requests)
    print("responses:", responses)
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


def append_prompt_to_history(prompt, previous_requests, previous_responses):
    chat = ""
    # Reconstruct the previous conversation, unless this is an embeddings model.
    if "gpt" in MODEL:
        messages = []
        for i in range(len(previous_requests)):
            request = previous_requests[i]
            response = ""
            response = previous_responses[i]["completion"]
            messages.append(("human", request))
            messages.append(("assistant", response))
        messages.append(("human", prompt))
        return messages
    else:
        if "embed" not in MODEL:
            for i in range(len(previous_requests)):
                request = previous_requests[i]
                response = ""
                response = previous_responses[i]["completion"]
                chat = chat + f"\n\nHuman: {request}"
                chat = chat + f"\n\nAssistant: {response}"
    # Append the most recent prompt to the end of the chat.
        return chat + f"\n\nHuman: {prompt}. \n\n Assistant:"


class Settings:
    def __init__(self, event, session):
        self.dynamodb_client = boto3.client("dynamodb")
        # Set up Bedrock client (special case -- we need to load from the environment).
        self.bedrock_runtime = session.client("bedrock-runtime")
        print("Initialized Bedrock client.")

        # Get config from the request body.
        body = json.loads(event["body"])
        self.prompt = body["prompt"]
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

def get_ws_user_name(table, connection_id):
    user_name = "guest"
    try:
        item_response = table.get_item(Key={"connection_id": connection_id})
        print(f'item_response: {item_response}')
        user_name = item_response["Item"]["user_name"]
        print("Got user name", user_name)
    except ClientError:
        print("Couldn't find user name. Using", user_name)
    return user_name


def get_connection_ids(table):
    connection_ids = []
    try:
        scan_response = table.scan(ProjectionExpression="connection_id")
        connection_ids = [item["connection_id"] for item in scan_response["Items"]]
        print(f"Found {len(connection_ids)} active connections.")
        return connection_ids
    except ClientError:
        print("Couldn't get connections.")
        return None


def post_to_ws(string, table, connection_id, other_conn_id, apigw_management_client):
    if DEBUG:  # Don't try send anything if we're debugging.
        return

    print("Posting string to websocket", string)
    try:
        send_response = apigw_management_client.post_to_connection(
            Data=string.encode("utf-8"), ConnectionId=other_conn_id
        )
        print(
            f"Posted message to connection {other_conn_id}, got websocket response {send_response}."
        )
    except ClientError:
        print("Couldn't post to connection", other_conn_id)
    except apigw_management_client.exceptions.GoneException:
        print(f"Connection {other_conn_id} is gone, removing.")
        try:
            table.delete_item(Key={"connection_id": other_conn_id})
        except ClientError:
            print("Couldn't remove connection", other_conn_id)


def handle_message(event, table, connection_id, event_body, apigw_management_client):
    """
    Handles messages sent by a participant in the chat. Looks up all connections
    currently tracked in the DynamoDB table, and uses the API Gateway Management API
    to post the message to each other connection.

    When posting to a connection results in a GoneException, the connection is
    considered disconnected and is removed from the table. This is necessary
    because disconnect messages are not always sent when a client disconnects.

    :param table: The DynamoDB connection table.
    :param connection_id: The ID of the connection that sent the message.
    :param event_body: The body of the message sent from API Gateway. This is a
                       dict with a `msg` field that contains the message to send.
    :param apigw_management_client: A Boto3 API Gateway Management API client.
    :return: An HTTP status code that indicates the result of posting the message
             to all active connections.
    """
    print("event:", event)

    # Get boto3 session and credentials
    session = boto3.Session()
    session._loader.search_paths.extend(["/root/.aws/models"])
    credentials = session.get_credentials()

    settings = Settings(event, session)

    if MODEL.startswith("gpt"):
        llm_chat = ChatOpenAI(
            model=MODEL,
            api_key=API_KEY,
            temperature=0
        )
    else:
        # Create a LangChain BedrockChat to stream the results.
        llm_chat = BedrockChat(
            model_id=MODEL,
            client=settings.bedrock_runtime,
            model_kwargs={
                "max_tokens_to_sample": 4096,
                "temperature": 0.0,
            },
        )

    # Set up the Websocket connection
    user_name = get_ws_user_name(table, connection_id)
    connection_ids = get_connection_ids(table)

    if (len(connection_ids) == 0) and not DEBUG:
        return 404

    # Get the chat history.
    chat_history = get_chat_history(settings.dynamodb_client, settings.chat_id)
    previous_requests = get_messages_from_history(chat_history, "requests")
    previous_responses = get_messages_from_history(chat_history, "responses")

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

        completion = cached_responses["completion"]
        full_response_json = {
            "completion": completion,
            "chat_id": settings.chat_id,
            "cached": "true",
            "has_more_messages": "false",
        }
        full_response_string = json.dumps(full_response_json)

        print("conn ids", connection_ids)
        for other_conn_id in connection_ids:
            post_to_ws(
                full_response_string,
                table,
                connection_id,
                other_conn_id,
                apigw_management_client,
            )
    else:
        full_chat = append_prompt_to_history(
            settings.prompt, previous_requests, previous_responses
        )

        full_completion = ""
        print("full_chat", full_chat)
        for chunk in llm_chat.stream(full_chat):
            partial_completion = chunk.content
            print(partial_completion)
            full_completion += partial_completion

            partial_response_json = {
                "completion": partial_completion,
                "chat_id": settings.chat_id,
                "cached": "false",
                "has_more_messages": "true",
            }
            partial_response_string = json.dumps(partial_response_json)

            for other_conn_id in connection_ids:
                post_to_ws(
                    partial_response_string,
                    table,
                    connection_id,
                    other_conn_id,
                    apigw_management_client,
                )

        terminal_response_json = {
            "completion": "",
            "chat_id": settings.chat_id,
            "cached": "false",
            "has_more_messages": "false",
        }
        terminal_response_string = json.dumps(terminal_response_json)
        for other_conn_id in connection_ids:
            post_to_ws(
                terminal_response_string,
                table,
                connection_id,
                other_conn_id,
                apigw_management_client,
            )

        # If this is the first message recieved, we should cache the response.
        full_response_json = {
            "completion": full_completion,
            "chat_id": settings.chat_id,
            "cached": "false",
        }
        if not previous_requests:
            post_to_cache(
                settings.dynamodb_client,
                settings.node_id,
                settings.prompt,
                full_response_json,
            )

    print("Combined responses sent to websocket", full_response_json)
    post_to_history(
        settings.dynamodb_client,
        settings.chat_id,
        MODEL,
        requests=[settings.prompt],
        responses=[full_response_json],
    )

    # Return success code
    return 200


## END NETWORK ANALYSIS ########################################################
## BEGIN WEBSOCKETS ############################################################


def handle_connect(user_name, table, connection_id):
    """
    Handles new connections by adding the connection ID and user name to the
    DynamoDB table.

    :param user_name: The name of the user that started the connection.
    :param table: The DynamoDB connection table.
    :param connection_id: The websocket connection ID of the new connection.
    :return: An HTTP status code that indicates the result of adding the connection
             to the DynamoDB table.
    """
    status_code = 200
    try:
        table.put_item(Item={"connection_id": connection_id, "user_name": user_name})
        logger.info("Added connection %s for user %s.", connection_id, user_name)
    except ClientError:
        logger.exception(
            'Couldn\'t add connection %s for user="%s".', connection_id, user_name
        )
        status_code = 503
    return status_code


def handle_disconnect(table, connection_id):
    """
    Handles disconnections by removing the connection record from the DynamoDB table.

    :param table: The DynamoDB connection table.
    :param connection_id: The websocket connection ID of the connection to remove.
    :return: An HTTP status code that indicates the result of removing the connection
             from the DynamoDB table.
    """
    status_code = 200
    try:
        table.delete_item(Key={"connection_id": connection_id})
        logger.info("Disconnected connection %s.", connection_id)
    except ClientError:
        logger.exception("Couldn't disconnect connection %s.", connection_id)
        status_code = 503
    return status_code


def lambda_handler(event, context):
    """
    An AWS Lambda handler that receives events from an API Gateway websocket API
    and dispatches them to various handler functions.

    This function looks up the name of a DynamoDB table in the `WEBSOCKET_CONNECTIONS_TABLE_NAME` environment
    variable. The table must have a primary key named `connection_id`.

    This function handles three routes: $connect, $disconnect, and sendmessage. Any
    other route results in a 404 status code.

    The $connect route accepts a query string `name` parameter that is the name of
    the user that originated the connection. This name is added to all chat messages
    sent by that user.

    :param event: A dict that contains request data, query string parameters, and
                  other data sent by API Gateway.
    :param context: Context around the request.
    :return: A response dict that contains an HTTP status code that indicates the
             result of handling the event.
    """
    table_name = os.environ["WEBSOCKET_CONNECTIONS_TABLE_NAME"]
    route_key = event.get("requestContext", {}).get("routeKey")
    print("route key", route_key)
    connection_id = event.get("requestContext", {}).get("connectionId")
    if not DEBUG:  # If we're debugging, we don't need these variables.
        if table_name is None or route_key is None or connection_id is None:
            return {"statusCode": 400}

    table = boto3.resource("dynamodb").Table(table_name)
    logger.info("Request: %s, use table %s.", route_key, table.name)

    response = {"statusCode": 200}
    if route_key == "$connect":
        user_name = event.get("queryStringParameters", {"name": "guest"}).get("name")
        print(f'username: {user_name}')
        response["statusCode"] = handle_connect(user_name, table, connection_id)
    elif route_key == "$disconnect":
        response["statusCode"] = handle_disconnect(table, connection_id)
    elif route_key == "sendmessage" or DEBUG:
        print("Handling message.")
        body = event.get("body")
        body = json.loads(body if body is not None else '{"prompt": ""}')
        domain = event.get("requestContext", {}).get("domainName")
        stage = event.get("requestContext", {}).get("stage")
        if (domain is None or stage is None) and not DEBUG:
            logger.warning(
                "Couldn't send message. Bad endpoint in request: domain '%s', "
                "stage '%s'",
                domain,
                stage,
            )
            response["statusCode"] = 400
        else:  # Either (1) we are debugging, or (2) `domain` & `stage` are set.
            apigw_management_client = boto3.client(
                "apigatewaymanagementapi", endpoint_url=f"https://{domain}/{stage}"
            )
            response["statusCode"] = handle_message(
                event, table, connection_id, body, apigw_management_client
            )
    else:
        response["statusCode"] = 404

    return response
