import time
import uuid
from abc import ABC, abstractmethod
from typing import AsyncIterable

from api.schema import (
    # Chat
    ChatResponse,
    ChatRequest,
    ChatStreamResponse,
    # Embeddings
    EmbeddingsRequest,
    EmbeddingsResponse,
)


class BaseChatModel(ABC):
    """Represent a basic chat model

    Currently, only Bedrock model is supported, but may be used for SageMaker models if needed.
    """

    def list_models(self) -> list[str]:
        """Return a list of supported models"""
        return []

    def validate(self, chat_request: ChatRequest):
        """Validate chat completion requests."""
        pass

    @abstractmethod
    def chat(self, chat_request: ChatRequest) -> ChatResponse:
        """Handle a basic chat completion requests."""
        pass

    @abstractmethod
    def chat_stream(self, chat_request: ChatRequest, user_name, api_key_name) -> AsyncIterable[bytes]:
        """Handle a basic chat completion requests with stream response."""
        pass

    @staticmethod
    def generate_message_id() -> str:
        return "chatcmpl-" + str(uuid.uuid4())[:8]

    @staticmethod
    def stream_response_to_bytes(
            response: ChatStreamResponse | None = None
    ) -> bytes:
        if response:
            # to populate other fields when using exclude_unset=True
            response.system_fingerprint = "fp"
            response.object = "chat.completion.chunk"
            response.created = int(time.time())
            return "data: {}\n\n".format(response.model_dump_json(exclude_unset=True)).encode("utf-8")
        return "data: [DONE]\n\n".encode("utf-8")


class BaseEmbeddingsModel(ABC):
    """Represents a basic embeddings model.

    Currently, only Bedrock-provided models are supported, but it may be used for SageMaker models if needed.
    """

    @abstractmethod
    def embed(self, embeddings_request: EmbeddingsRequest, user_name:str, api_key_name:str) -> EmbeddingsResponse:
        """Handle a basic embeddings request."""
        pass
