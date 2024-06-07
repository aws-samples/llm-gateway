from typing import Annotated

from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse

from api.auth import api_key_auth, get_api_key_name
from api.models import get_model
from api.schema import ChatRequest, ChatResponse, ChatStreamResponse
from api.setting import DEFAULT_MODEL
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.quota import check_quota
from api.model_access import check_model_access

router = APIRouter(
    prefix="/chat",
    #dependencies=[Depends(api_key_auth)],
    # responses={404: {"description": "Not found"}},
)

security = HTTPBearer()


@router.post("/completions", response_model=ChatResponse | ChatStreamResponse, response_model_exclude_none=True)
async def chat_completions(
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
    user_name = api_key_auth(credentials)
    api_key_name = None
    if credentials.credentials.startswith("sk-"):
        api_key_name = get_api_key_name(credentials.credentials)

    check_model_access(user_name, api_key_name, chat_request.model)
    check_quota(user_name)

    if chat_request.model.lower().startswith("gpt-"):
        chat_request.model = DEFAULT_MODEL
        
    # Exception will be raised if model not supported.
    model = get_model(chat_request.model)
    if chat_request.stream:
        return StreamingResponse(
            content=model.chat_stream(chat_request, user_name, api_key_name), media_type="text/event-stream"
        )
    return model.chat(chat_request)
