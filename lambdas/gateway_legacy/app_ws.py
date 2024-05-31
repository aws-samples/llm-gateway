from botocore.exceptions import ClientError
from common import Settings, append_prompt_to_history, get_chat_history, get_llm_chat, get_messages_from_history, get_salt, get_user_name, handle_cache, has_exceeded_rate_limit, post_to_cache, post_to_history
import boto3
import json
import logging
import os
from langchain_core.messages import AIMessage

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ## BEGIN ENVIORNMENT VARIABLES #################################################
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

def get_ws_user_name(table, connection_id):
    try:
        item_response = table.get_item(Key={"connection_id": connection_id})
        print(f'item_response: {item_response}')
        if item_response.get("Item"):
            user_name = str(item_response["Item"].get("user_name"))
            print("Got user name", user_name)
    except (ClientError,KeyError):
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

def post_to_ws(string, table, connection_id, apigw_management_client):
    if DEBUG:  # Don't try send anything if we're debugging.
        return

    print("Posting string to websocket", string)
    try:
        send_response = apigw_management_client.post_to_connection(
            Data=string.encode("utf-8"), ConnectionId=connection_id
        )
        print(
            f"Posted message to connection {connection_id}, got websocket response {send_response}."
        )
    except ClientError:
        print("Couldn't post to connection", connection_id)
    except apigw_management_client.exceptions.GoneException:
        print(f"Connection {connection_id} is gone, removing.")
        try:
            table.delete_item(Key={"connection_id": connection_id})
        except ClientError:
            print("Couldn't remove connection", connection_id)

def handle_message(event, table, connection_id, apigw_management_client):
    """
    Handles messages sent by a participant in the chat. Looks up all connections
    currently tracked in the DynamoDB table, and uses the API Gateway Management API
    to post the message to each other connection.

    When posting to a connection results in a GoneException, the connection is
    considered disconnected and is removed from the table. This is necessary
    because disconnect messages are not always sent when a client disconnects.

    :param table: The DynamoDB connection table.
    :param connection_id: The ID of the connection that sent the message.
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
    
    llm_chat = get_llm_chat(settings)
    if not llm_chat:
        return 400

    # Set up the Websocket connection
    user_name = get_ws_user_name(table, connection_id)
    print(f'ws_user_name: {user_name}')

    if has_exceeded_rate_limit(user_name):
        full_response_json = {
            "completion": "Rate limit exceeded.",
            "chat_id": settings.chat_id,
            "cached": "false",
            "has_more_messages": "false",
        }
        full_response_string = json.dumps(full_response_json)
        post_to_ws(
            full_response_string,
            table,
            connection_id,
            apigw_management_client,
        )
        return 429

    # Get the chat history.
    chat_history = get_chat_history(settings.dynamodb_client, settings.chat_id)
    previous_requests = get_messages_from_history(chat_history, "requests")
    previous_responses = get_messages_from_history(chat_history, "responses")

    # Check if we have answered this question before for this node.
    cached_responses = handle_cache(settings, previous_requests)
    if cached_responses:
        completion = cached_responses["completion"]
        full_response_json = {
            "completion": completion,
            "chat_id": settings.chat_id,
            "cached": "true",
            "has_more_messages": "false",
        }
        full_response_string = json.dumps(full_response_json)

        print("conn id", connection_id)
        post_to_ws(
            full_response_string,
            table,
            connection_id,
            apigw_management_client,
        )
    else:
        full_chat = append_prompt_to_history(
            settings.prompt, previous_requests, previous_responses, settings.model,
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

            post_to_ws(
                partial_response_string,
                table,
                connection_id,
                apigw_management_client,
            )

        terminal_response_json = {
            "completion": "",
            "chat_id": settings.chat_id,
            "cached": "false",
            "has_more_messages": "false",
        }
        terminal_response_string = json.dumps(terminal_response_json)
        post_to_ws(
            terminal_response_string,
            table,
            connection_id,
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

    full_chat.append(AIMessage(content=full_completion))
    post_to_history(
        settings.dynamodb_client,
        settings.chat_id,
        settings.model,
        history=full_chat,
    )

    # Return success code
    return 200

## END NETWORK ANALYSIS ########################################################
## BEGIN WEBSOCKETS ############################################################

def handle_connect(event, table, connection_id):
    headers = event["headers"]
    print(f'headers: {headers}')
    user_name = ""
    if not headers or "Authorization" not in headers:
        print(f"Can't find Authorization header")
    else:
        authorization_header = headers["Authorization"]
        print(f"authorization_header: {authorization_header}")
        user_name = get_user_name(authorization_header)

    print(f'username: {user_name}')
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
        response["statusCode"] = handle_connect(event, table, connection_id)
    elif route_key == "$disconnect":
        response["statusCode"] = handle_disconnect(table, connection_id)
    elif route_key == "sendmessage" or DEBUG:
        print("Handling message.")
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
                event, table, connection_id, apigw_management_client,
            )
    else:
        response["statusCode"] = 404

    return response
