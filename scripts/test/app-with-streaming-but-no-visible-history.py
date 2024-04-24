import streamlit as st
import asyncio
import websockets
import json

uri = "wss://8b9ldf1092.execute-api.us-east-1.amazonaws.com/prod"

message_input = st.text_input("Type a message:")

# Initialize chat_id in session state
if 'chat_id' not in st.session_state:
    st.session_state.chat_id = None

if st.button("Send"):
    completion_string = ""
    output_container = st.empty()  # Create an empty container

    async def send_message():
        global completion_string  # Access the global variable
        async with websockets.connect(uri) as socket:
            message = {"action": "sendmessage", "prompt": message_input}
            if st.session_state.chat_id:
                message["chat_id"] = st.session_state.chat_id
            await socket.send(json.dumps(message))
            while True:
                response = await socket.recv()
                response_json = json.loads(response)
                completion = response_json.get("completion")
                st.session_state.chat_id = response_json.get("chat_id")
                if completion:
                    completion_string += completion
                    output_container.write(completion_string)  # Update the container
                if response_json.get("has_more_messages") == "false":
                    break

    asyncio.run(send_message())