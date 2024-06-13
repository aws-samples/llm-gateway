from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from api.auth import api_key_auth
from api.models import SUPPORTED_BEDROCK_MODELS, SUPPORTED_BEDROCK_EMBEDDING_MODELS
from api.schema import Models, Model
from api.model_access import get_allowed_model_list

router = APIRouter(
    prefix="/models",
    #dependencies=[Depends(api_key_auth)],
    # responses={404: {"description": "Not found"}},
)

security = HTTPBearer()

async def validate_model_id(model_id: str):
    if model_id not in (SUPPORTED_BEDROCK_MODELS | SUPPORTED_BEDROCK_EMBEDDING_MODELS).keys():
        raise HTTPException(status_code=500, detail="Unsupported Model Id")


@router.get("", response_model=Models)
async def list_models(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    user_name = api_key_auth(credentials)
    allowed_model_list = get_allowed_model_list(user_name)
    supported_model_list = SUPPORTED_BEDROCK_MODELS.keys() | SUPPORTED_BEDROCK_EMBEDDING_MODELS.keys()
    available_model_list = list(set(allowed_model_list) & set(supported_model_list))

    models = [Model(id=model_id) for model_id in available_model_list]
    
    return Models(data=models)


@router.get(
    "/{model_id}",
    response_model=Model,
)
async def get_model(
        model_id: Annotated[
            str,
            Path(description="Model ID", example="anthropic.claude-3-sonnet-20240229-v1:0"),
        ],
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
):
    user_name = api_key_auth(credentials)
    await validate_model_id(model_id)
    return Model(id=model_id)
