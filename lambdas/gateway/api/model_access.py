from typing import List
from fastapi import HTTPException, status
import datetime
import os
from cachetools import TTLCache
import boto3
from boto3.dynamodb.conditions import Key
import json
import pandas as pd
from botocore.exceptions import ClientError
import decimal
from api.request_details import create_request_detail

DEFAULT_MODEL_ACCESS_PARAMETER_NAME = os.environ.get("DEFAULT_MODEL_ACCESS_PARAMETER_NAME")
REGION = os.environ.get("REGION")
MODEL_ACCESS_TABLE_NAME = os.environ.get("MODEL_ACCESS_TABLE_NAME")
ssm_client = boto3.client("ssm")

cache = TTLCache(maxsize=10000, ttl=1200)
default_model_access_cache = TTLCache(maxsize=1, ttl=1200)

dynamodb = boto3.resource('dynamodb')
model_access_table = dynamodb.Table(MODEL_ACCESS_TABLE_NAME)

def check_model_access(user_name, api_key_name, model_id):
    allowed_models_list = get_allowed_model_list(user_name)
    #print(f'model_id: {model_id} allowed_models_list: {allowed_models_list}')
    if model_id not in allowed_models_list:
        create_request_detail(user_name, api_key_name, None, None, None, model_id, "Model Access Denied")
        raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN, detail=f"User does not have access to selected model"
                    )
    #print(f'User has access to model. Processing request.')


def get_allowed_model_list(user_name) -> List[str]:
    #('Checking if user has has access to model')
    model_access_config = get_from_cache(user_name)

    if not model_access_config:
        #print("No cached model access, getting user's model access config")
        model_access_config = get_user_model_access_config(user_name)
        
        if not model_access_config:
            #print('No user specific config, getting default model access config')
            model_access_config = get_default_model_access()
            if model_access_config:
                pass
                #print(f'Found default model access config: {model_access_config}')
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Model access config not configured correctly"
                )
        else:
            pass

        add_to_cache(user_name, model_access_config)
    else:
        pass
        #print(f'model access config cache hit')

    return model_access_config["model_access_list"].split(",")

def get_user_model_access_config(user_name):
    response = model_access_table.query(
        KeyConditionExpression=Key('username').eq(user_name)
    )
    #print(f'response: {response}')
    #print(f'response: {response["Items"]}')
    if not response["Items"]:
        return None

    return response["Items"][0]["model_access_map"]

def add_to_cache(key, value):
    cache[key] = value

def get_from_cache(key):
    return cache.get(key, None)

def get_default_model_access():
    default_model_access_dict = default_model_access_cache.get("default", None)
    if default_model_access_dict:
        return default_model_access_dict
    
    response = ssm_client.get_parameter(Name=DEFAULT_MODEL_ACCESS_PARAMETER_NAME, WithDecryption=True)
    parameter_value = response['Parameter']['Value']
    default_model_access_dict = json.loads(parameter_value)
    default_model_access_cache["default"] = default_model_access_dict
    return default_model_access_dict