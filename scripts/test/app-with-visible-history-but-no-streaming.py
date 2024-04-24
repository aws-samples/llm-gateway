import os
import streamlit as st
from openai import OpenAI
import websockets
import json
import asyncio

client = OpenAI()
uri = "wss://8b9ldf1092.execute-api.us-east-1.amazonaws.com/prod"

# Display the chat history
def create_chat_area(chat_history):
    for chat in chat_history:
        role = chat['role']
        with st.chat_message(role):
            st.write(chat['content'])

async def chat(messages):
    async with websockets.connect(uri) as socket:
        message = {"action": "sendmessage", "prompt": messages}
        if st.session_state.chat_id:
            message["chat_id"] = st.session_state.chat_id
        await socket.send(json.dumps(message))
        while True:
            response = await socket.recv()
            response_json = json.loads(response)
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
        st.experimental_rerun()

    # Handle user input and generate assistant response
    if user_input or st.session_state.streaming:
        process_user_input(user_input)

def process_user_input(user_input):
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        gpt_answer = chat(user_input)
        st.session_state.generator = gpt_answer
        st.session_state.streaming = True
        st.session_state.chat_history.append({"role": "assistant", "content": ''})
        st.experimental_rerun()
    else:
        asyncio.run(update_assistant_response())

async def update_assistant_response():
    try:
        generator = st.session_state.generator
        while True:
            chunk = await anext(generator)
            st.session_state.chat_history[-1]["content"] += chunk
    except StopAsyncIteration:
        st.session_state.streaming = False
    st.experimental_rerun()



if __name__ == '__main__':
    main()