from typing import Annotated

from fastapi import APIRouter, Depends, Body, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from api.auth import api_key_auth, get_api_key_name
from api.models.bedrock import BedrockModel
from api.schema import ChatRequest, ChatResponse, ChatStreamResponse
from api.setting import DEFAULT_MODEL
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.quota import check_quota
from api.model_access import check_model_access
from api.model_enabled import get_model_region_map

router = APIRouter(
    prefix="/chat",
    #dependencies=[Depends(api_key_auth)],
    # responses={404: {"description": "Not found"}},
)

security = HTTPBearer()

model_region_map = get_model_region_map()

@router.post("/completions", response_model=ChatResponse | ChatStreamResponse, response_model_exclude_unset=True)
def chat_completions(
        request: Request,
        chat_request: Annotated[
            ChatRequest,
            Body(
                examples=[
                    {
                        "model": "anthropic.claude-3-sonnet-20240229-v1:0",
                        "messages": [
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": "Hello!"},
                        ],
                    }
                ],
            ),
        ],
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
):
    current_path = request.url.path
    user_name, error_response =  api_key_auth(credentials, current_path)
    if error_response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key or JWT Cognito Access Token"
        )

    api_key_name = None
    if credentials.credentials.startswith("sk-"):
        api_key_name = get_api_key_name(credentials.credentials)

    if chat_request.model not in model_region_map:
        raise HTTPException(status_code=400, detail=str("Selected model is not enabled"))

    check_model_access(user_name, api_key_name, chat_request.model)
    check_quota(user_name, api_key_name, chat_request.model)

    if chat_request.model.lower().startswith("gpt-"):
        chat_request.model = DEFAULT_MODEL
        
    # Exception will be raised if model not supported.
    model = BedrockModel()
    model.validate(chat_request)
    if chat_request.stream:
        return StreamingResponse(
            content=model.chat_stream(chat_request, user_name, api_key_name), media_type="text/event-stream"
        )
    try:
        return model.chat(chat_request, user_name, api_key_name)
    except Exception as e:
        print(f'exception: {e}')
