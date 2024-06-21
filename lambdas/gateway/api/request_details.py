import os
import boto3
from datetime import datetime, timezone
import logging
from api.setting import DEBUG
import decimal

REQUEST_DETAILS_TABLE_NAME = os.environ.get("REQUEST_DETAILS_TABLE_NAME")

table = boto3.resource("dynamodb").Table(REQUEST_DETAILS_TABLE_NAME)
logger = logging.getLogger(__name__)

def get_current_timestamp():
    return datetime.now(timezone.utc).isoformat()

def create_request_detail(username, api_key_name, estimated_cost, input_tokens, output_tokens, model_id, result):
    item = {
            'username': username,
            'timestamp': get_current_timestamp(),
            'model_id': model_id,
            'result': result
        }

    if api_key_name:
        item['api_key_name'] = api_key_name
    if estimated_cost:
        item['estimated_cost'] = decimal.Decimal(str(estimated_cost))
    if input_tokens:
        item['input_tokens'] = decimal.Decimal(str(input_tokens))
    if output_tokens:
        item['output_tokens'] = decimal.Decimal(str(output_tokens))
    if DEBUG:
        logger.info(item)
    dynamo_response = table.put_item(
            Item=item
    )
    #print("Item created successfully:", dynamo_response)