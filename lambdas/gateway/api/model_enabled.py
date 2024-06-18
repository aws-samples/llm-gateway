import boto3
import os


ENABLED_MODELS = os.environ["ENABLED_MODELS"]
print(f'ENABLED_MODELS: {ENABLED_MODELS}')
REGION = os.environ["REGION"]

enabled_models_list = ENABLED_MODELS.split(",")
print(f'enabled_models_list: {enabled_models_list}')
region_client_map = {}
model_region_map = {}

for enabled_model in enabled_models_list:
    print(f'enabled_model: {enabled_model}')
    enabled_model_split = enabled_model.split("_")
    if len(enabled_model_split) == 1:
        region = REGION
        model = enabled_model_split[0]
    else:
        region = enabled_model_split[0]
        model = enabled_model_split[1]

    if region not in region_client_map:
        region_client_map[region] = boto3.client(
            service_name="bedrock-runtime",
            region_name=region,
        )
    model_region_map[model] = region

print(f'region_client_map: {region_client_map}')
print(f'model_region_map: {model_region_map}')

def get_model_region_map():
    return model_region_map

def get_region_client_map():
    return region_client_map
