from typing import Annotated

from fastapi import APIRouter, Depends, Body, HTTPException, Request, status

from api.auth import api_key_auth, get_api_key_name
from api.models.bedrock import get_embeddings_model
from api.schema import EmbeddingsRequest, EmbeddingsResponse
from api.setting import DEFAULT_EMBEDDING_MODEL
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.model_access import check_model_access
from api.quota import check_quota
from api.model_enabled import get_model_region_map

router = APIRouter(
    prefix="/embeddings",
    #dependencies=[Depends(api_key_auth)],
)

security = HTTPBearer()

model_region_map = get_model_region_map()

@router.post("", response_model=EmbeddingsResponse)
async def embeddings(
        request: Request,
        embeddings_request: Annotated[
            EmbeddingsRequest,
            Body(
                examples=[
                    {
                        "model": "cohere.embed-multilingual-v3",
                        "input": [
                            "Your text string goes here"
                        ],
                    }
                ],
            ),
        ],
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
):
    if embeddings_request.model.lower().startswith("text-embedding-"):
        embeddings_request.model = DEFAULT_EMBEDDING_MODEL
    current_path = request.url.path

    user_name, error_response =  api_key_auth(credentials, current_path)
    if error_response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key or JWT Cognito Access Token"
        )

    if credentials.credentials.startswith("sk-"):
        api_key_name = get_api_key_name(credentials.credentials)

    if embeddings_request.model not in model_region_map:
        raise HTTPException(status_code=400, detail=str("Selected model is not enabled"))

    check_model_access(user_name, api_key_name, embeddings_request.model)
    check_quota(user_name, api_key_name, embeddings_request.model)
    # Exception will be raised if model not supported.
    model = get_embeddings_model(embeddings_request.model)
    return model.embed(embeddings_request)