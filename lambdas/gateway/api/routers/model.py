from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from api.auth import api_key_auth
from api.models.bedrock import BedrockModel
from api.schema import Models, Model
from api.model_access import get_allowed_model_list

router = APIRouter(
    prefix="/models",
    #dependencies=[Depends(api_key_auth)],
    # responses={404: {"description": "Not found"}},
)

security = HTTPBearer()

chat_model = BedrockModel()

async def validate_model_id(model_id: str):
    if model_id not in chat_model.list_models():
        raise HTTPException(status_code=500, detail="Unsupported Model Id")


@router.get("", response_model=Models)
async def list_models(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
    ):
    current_path = request.url.path

    user_name, error_response =  api_key_auth(credentials, current_path)
    if error_response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key or JWT Cognito Access Token"
        )

    allowed_model_list = get_allowed_model_list(user_name)
    supported_model_list = chat_model.list_models()
    available_model_list = list(set(allowed_model_list) & set(supported_model_list))
    model_list = [Model(id=model_id) for model_id in available_model_list]
    return Models(data=model_list)


@router.get(
    "/{model_id}",
    response_model=Model,
)
async def get_model(
        request: Request,
        model_id: Annotated[
            str,
            Path(description="Model ID", example="anthropic.claude-3-sonnet-20240229-v1:0"),
        ],
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
):
    current_path = request.url.path

    user_name, error_response =  api_key_auth(credentials, current_path)
    if error_response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key or JWT Cognito Access Token"
        )
    await validate_model_id(model_id)
    return Model(id=model_id)
