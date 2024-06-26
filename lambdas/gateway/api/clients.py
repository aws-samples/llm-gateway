import botocore
import boto3

client_config = botocore.config.Config(
            max_pool_connections=1000,
        )
dynamodb = boto3.resource('dynamodb', config=client_config)

def get_dynamo_db_client():
    return dynamodb