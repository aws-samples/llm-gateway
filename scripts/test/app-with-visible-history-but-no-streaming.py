import os
import streamlit as st
from openai import OpenAI
import websockets
import json
import asyncio
import logging

client = OpenAI()
uri = "wss://8b9ldf1092.execute-api.us-east-1.amazonaws.com/prod"
logging.basicConfig(level=logging.INFO)
# Display the chat history
def create_chat_area(chat_history):
    for chat in chat_history:
        role = chat['role']
        with st.chat_message(role):
            st.write(chat['content'])

async def ensure_websocket_connection():
    if 'websocket' not in st.session_state or st.session_state.websocket.closed:
        st.session_state.websocket = await websockets.connect(uri)
    return st.session_state.websocket

async def chat(messages):
    socket = await ensure_websocket_connection()
    message = {"action": "sendmessage", "prompt": messages}
    if st.session_state.chat_id:
        message["chat_id"] = st.session_state.chat_id
    await socket.send(json.dumps(message))
    while True:
        response = await socket.recv()
        response_json = json.loads(response)
        print(f'response_json: {response_json}')
        completion = response_json.get("completion")
        st.session_state.chat_id = response_json.get("chat_id")
        if completion:
            yield completion
        if response_json.get("has_more_messages") == "false":
            break

# Main function to run the Streamlit app
def main():
    # Streamlit settings
    st.markdown("""<style>.block-container{max-width: 66rem !important;}</style>""", unsafe_allow_html=True)
    st.title("ChatGpt Streamlit Demo")
    st.markdown('---')

    # Session state initialization
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'streaming' not in st.session_state:
        st.session_state.streaming = False
    if 'chat_id' not in st.session_state:
        st.session_state.chat_id = None  # Initialize chat_id as None

    # API key setup
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key is None:
        with st.sidebar:
            st.subheader("Settings")
            openai_key = st.text_input("Enter your OpenAI key:", type="password")
    elif openai_key:
        run_chat_interface()
    else:
        st.error("Please enter your OpenAI key in the sidebar to start.")

# Run the chat interface within Streamlit
def run_chat_interface():
    create_chat_area(st.session_state.chat_history)

    # Chat controls
    clear_button = st.button("Clear Chat History") if len(st.session_state.chat_history) > 0 else None
    user_input = st.chat_input("Ask something:")

    # Clear chat history
    if clear_button:
        st.session_state.chat_history = []
        st.session_state.chat_id = None
        st.rerun()

    # Handle user input and generate assistant response
    if user_input or st.session_state.streaming:
        process_user_input(user_input)

def process_user_input(user_input):
    logging.info(f'user_input: {user_input}')
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        gpt_answer = chat(user_input)
        st.session_state.generator = gpt_answer
        st.session_state.streaming = True
        st.session_state.chat_history.append({"role": "assistant", "content": ''})
        st.rerun()
    else:
        asyncio.run(update_assistant_response())

async def update_assistant_response():
    try:
        generator = st.session_state.generator
        while True:
            chunk = await anext(generator)
            logging.info(f'chunk: {chunk}')
            st.session_state.chat_history[-1]["content"] += chunk
            st.rerun()
    except StopAsyncIteration:
        logging.info("StopAsyncIteration")
        st.session_state.streaming = False
    



if __name__ == '__main__':
    if 'websocket' not in st.session_state:
        asyncio.run(ensure_websocket_connection())  # Ensure WebSocket connection on start
    main()