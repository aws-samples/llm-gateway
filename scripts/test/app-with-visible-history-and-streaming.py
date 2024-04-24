import streamlit as st
from invoke_llm_with_streaming import llm_answer_streaming
import asyncio
import threading
import queue
import websockets

uri = "wss://8b9ldf1092.execute-api.us-east-1.amazonaws.com/prod"

def bridge(async_gen, sync_queue):
    async def run():
        async for item in async_gen:
            sync_queue.put(item)
        sync_queue.put(None)  # Signal that the generator is done

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    loop.close()

def sync_generator(sync_queue):
    while True:
        item = sync_queue.get()
        if item is None:
            break
        yield item

# Title displayed on the streamlit web app
st.title(f""":rainbow[Bedrock Streaming API Sample]""")
# configuring values for session state
if "messages" not in st.session_state:
    st.session_state.messages = []
# writing the message that is stored in session state
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
# adding some special effects from the UI perspective
#st.balloons()
# evaluating st.chat_input and determining if a question has been input
if question := st.chat_input("Ask me about anything...and I will STREAM the answer!"):
    # with the user icon, write the question to the front end
    with st.chat_message("user"):
        st.markdown(question)
    # append the question and the role (user) as a message to the session state
    st.session_state.messages.append({"role": "user",
                                      "content": question})
    # respond as the assistant with the answer
    with st.chat_message("assistant"):
        q = queue.Queue()
        # Start the background thread
        thread = threading.Thread(target=bridge, args=(llm_answer_streaming(question), q))
        thread.start()
        # making sure there are no messages present when generating the answer
        message_placeholder = st.empty()
        # calling the invoke_llm_with_streaming to generate the answer as a generator object, and using
        # st.write stream to perform the actual streaming of the answer to the front end
        answer = st.write_stream(sync_generator(q))
    # appending the final answer to the session state
    st.session_state.messages.append({"role": "assistant",
                                      "content": answer})
    
