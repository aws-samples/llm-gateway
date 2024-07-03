import os
import boto3
from datetime import datetime, timezone
import logging
from api.setting import DEBUG
import decimal
from api.clients import get_dynamo_db_client

REQUEST_DETAILS_TABLE_NAME = os.environ.get("REQUEST_DETAILS_TABLE_NAME")

dynamodb = get_dynamo_db_client()
table = dynamodb.Table(REQUEST_DETAILS_TABLE_NAME)
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
        log_item = item.copy()
        if 'estimated_cost' in log_item:
            log_item['estimated_cost'] = f"{float(log_item['estimated_cost']):.15f}"
        if 'input_tokens' in log_item:
            log_item['input_tokens'] = float(log_item['input_tokens'])
        if 'output_tokens' in log_item:
            log_item['output_tokens'] = float(log_item['output_tokens'])

        print(log_item)

    dynamo_response = table.put_item(
            Item=item
    )
    #print("Item created successfully:", dynamo_response)