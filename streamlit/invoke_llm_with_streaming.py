import os
from dotenv import load_dotenv
import threading
import openai

# loading in environment variables
load_dotenv()


LlmGatewayUrl = os.environ["LlmGatewayUrl"] + "/api/v1"
print(f'LlmGatewayUrl: {LlmGatewayUrl}')

class ThreadSafeSessionState:
    def __init__(self):
        self.lock = threading.Lock()
        self.session_state = {}

    def get(self, key):
        with self.lock:
            return self.session_state.get(key)

    def set(self, key, value):
        with self.lock:
            self.session_state[key] = value
    def delete(self, key):
        with self.lock:
            del self.session_state[key]

thread_safe_session_state = ThreadSafeSessionState()

async def llm_answer_streaming(question, model, access_token):
    client = openai.AsyncOpenAI(base_url=LlmGatewayUrl, api_key=access_token)

    if thread_safe_session_state.get("chat_id"):
        chat_id = thread_safe_session_state.get("chat_id")
        # ToDo: Restore chat_id functionality to support server side history
        #message["chat_id"] = thread_safe_session_state.get("chat_id")
        print(f'found chat id {chat_id} in context')
    else:
        print(f'did not find chat id in context')

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": question}],
            max_tokens=1000,
            temperature=1,
            n=1,
            stream=True
        )
        # ToDo: Restore chat_id functionality to support server side history
        # print(f'Assigning chat id: {response_json.get("chat_id")}')
        # thread_safe_session_state.set("chat_id", response_json.get("chat_id"))
        async for chunk in stream:
            try:
                yield chunk.choices[0].delta.content if chunk.choices[0].finish_reason != "stop" else ''
            except:
                yield 'Error while processing the response!'
    except openai.APIError as e:
        if e.status_code == 429:
            yield e.message  # Return the error message from the API
        else:
            yield f'API error occurred: {e.status_code} - {e.message}'
    except Exception as e:
        print(f"Caught an exception of type: {type(e).__name__}")
        yield f'An unexpected error occurred: {str(e)} of type: {type(e).__name__}'

