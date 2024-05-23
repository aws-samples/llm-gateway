import streamlit as st
from invoke_llm_with_streaming import llm_answer_streaming
import asyncio
import threading
import queue
import websockets
import warnings
import boto3
from streamlit_float import *
from streamlit.web.server.websocket_headers import _get_websocket_headers
import jwt

st.set_page_config(layout="wide")
float_init(theme=True, include_unstable_primary=False)

# Initialize session state.
if "messages" not in st.session_state:
    st.session_state.messages = []
if "estimated_usage" not in st.session_state:
    st.session_state.estimated_usage = 0
# Inialize global variables.
quota_limit = 0.0001

quota_limit = 0.0001
is_streaming = False

################################################################################
# BEGIN - Lambda code - This needs to be migrated to the cloud
################################################################################

import re
import csv

ANY_WORD = "([a-zA-Z]+)"
UP_TO_3_DIGITS = "([\d]{1,3})"
PUNCTUATION = ".?!,\/\(\);:~=@%'\n"
UP_TO_3_PUNCTUATION = f"([{PUNCTUATION}]{1,3}+(?=(.?.?.?)*))"
ANY_NON_ASCII_CHAR = "(\\\\x[0-9a-fA-F]{2})"

PATTERN = f"{ANY_WORD}|{UP_TO_3_DIGITS}|{ANY_NON_ASCII_CHAR}|{UP_TO_3_PUNCTUATION}"

COST_DB = "data/cost_db.csv"
if 'model_id' not in st.session_state:
    st.session_state['model_id'] = None

def process_session_token():
    '''
    WARNING: We use unsupported features of Streamlit
             However, this is quite fast and works well with
             the latest version of Streamlit (1.27)
             Also, this does not verify the session token's
             authenticity. It only decodes the token.
    '''
    headers = _get_websocket_headers()
    if not headers or "X-Amzn-Oidc-Data" not in headers:
        return {}
    return jwt.decode(
        headers["X-Amzn-Oidc-Data"], algorithms=["ES256"], options={"verify_signature": False}
    )

session_token = process_session_token()
#st.write(f'session_token: {session_token}')

if "username" in session_token:
    username = session_token["username"]
else:
    username = "Could not find username. Normal if you are running locally."


def initialize_dependent_values():
    # Initialize or reset values that are dependent on main_column
    st.session_state['model_id'] = "anthropic.claude-3-sonnet-20240229-v1:0"  # Placeholder or default

def get_estimated_tokens(s: str) -> int:
    """
    Counts the number of tokens in the given string `s`, according to the
    following method:

    - All words (characters in [a-zA-Z] separated by whitespace or _, count as 1 token.
    - Numbers and punctuation are put into groups of 1-3 digits. Each group counts as 1 token.
    - All non ascii characters count as 1 token per byte.
    """

    s_encoded = s.encode("utf-8")

    result = re.findall(PATTERN, str(s_encoded)[2:])
    return [item for tup in result for item in tup if item]


def has_quota():
    return not (
        st.session_state.estimated_usage and
        st.session_state.estimated_usage > quota_limit
    )


def estimate_cost(
    model: str,
    region: str,
    type_: str,
    string: str,
    use_cache:bool=False,
) -> float:
    if type_ not in ["input", "output"]:
        raise Exception("`type_` must be one of [\"input\", \"output\"]")

    key = ",".join([model, region, type_])

    if use_cache:  # Skip the DDB step for better cost / time performance
        with open(COST_DB) as f:
            reader = csv.DictReader(f)
            costs_dict = {}
            for row in reader:
                model_name = row["model_name"]
                type_ = row["type"]
                region = row["region"]
                cost = float(row["cost_per_token"])

                costs_dict[",".join([model_name,region,type_])] = cost

            cost_per_k_tokens = costs_dict.get(key)

            if not cost_per_k_tokens:
                print(costs_dict)
                raise Exception(
                    f"Could not find ({model}, {region}, {type_}) in cost DB."
                )

            cost_per_token = cost_per_k_tokens / 1000
    else:  # Lookup in DDB
        raise NotImplemented()

    n_tokens = len(get_estimated_tokens(string))

    return cost_per_token * n_tokens

################################################################################
# END - Lambda code
################################################################################

metrics = {
    "n_input_tokens": 0,
    "n_output_tokens": 0,
    "input_cost": 0,
    "output_cost": 0,
}


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


def update_metrics(s, type_):
    print(metrics)
    metrics[f"n_{type_}_tokens"] = len(get_estimated_tokens(s))
    metrics[f"{type_}_cost"] = estimate_cost(
        "anthropic.claude-instant",
        "us-east-1",
        type_,
        s,
        use_cache=True
    )
    print(metrics)


# Create two columns
main_column, right_column = st.columns([3, 1])
if "is_responding" not in st.session_state:
    st.session_state.is_responding = False


def chat_content():
    # append the prompt and the role (user) as a message to the session state
    if "answer" in st.session_state:
        st.session_state.messages.append({"role": "assistant", "content": st.session_state.answer or "Quota limit exceeded." })
    if len(messages) == 0:
        st.session_state.messages.append({"role": "user", "content": st.session_state.prompt})
    st.session_state.is_responding = True

with main_column:
    st.title(f""":rainbow[LLM Gateway API Sample]""")

    if st.session_state.model_id == None:
        initialize_dependent_values()

    if messages := st.session_state.messages:
        if len(messages) > 1:
            st.session_state.messages.append({"role": "user", "content": st.session_state.prompt})

        if len(messages) > 1:
            print(st.session_state.messages)
            for message in st.session_state.messages[:-1]:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])


    if st.session_state.is_responding:
        # writing the message that is stored in session state
        if len(messages) > 0:
            message = st.session_state.messages[-1]
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        # respond as the assistant with the answer
        with st.chat_message("assistant"):
            q = queue.Queue()

            if has_quota():
                # Update the input metrics.
                update_metrics(st.session_state.prompt, "input")

                # Start the background thread

                print(f'st.session_state.model_id: {st.session_state.model_id}')
                thread = threading.Thread(
                    target=bridge,
                    args=(
                        llm_answer_streaming(
                            st.session_state.prompt,
                            st.session_state.model_id
                        ),
                        q,
                    )
                )
                thread.start()
                # making sure there are no messages present when generating the answer
                message_placeholder = st.empty()
                # calling the invoke_llm_with_streaming to generate the answer as a generator object, and using
                # st.write stream to perform the actual streaming of the answer to the front end
                st.session_state.answer = st.write_stream(sync_generator(q))
            else:
                st.session_state.answer = st.write("Quota limit exceeded.")
            is_responding = False

            # appending the final answer to the session state
            if "answer" in st.session_state:
                if has_quota():
                    update_metrics(st.session_state.answer, "output")
                    print(st.session_state.estimated_usage)
                    st.session_state.estimated_usage += metrics["input_cost"]
                    st.session_state.estimated_usage += metrics["output_cost"]

    st.chat_input("Ask me about anything...", key='prompt', on_submit=chat_content)


with right_column:
    # Control items
    is_streaming = st.toggle("Stream responses?")

    st.header("Usage Statistics")
    # Your usage statistics functionality goes here

    provider_options = ["Amazon Bedrock", "Azure & OpenAI"]
    provider = st.selectbox("Provider", provider_options)

    model_map = {
            "Claude 3 Sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
            "Claude 3 Haiku": "anthropic.claude-3-haiku-20240307-v1:0",
            "Llama 3": "meta.llama3-70b-instruct-v1:0",
            "Amazon Titan G1 Express": "amazon.titan-text-express-v1",
            "Mixtral 8x7B Instruct": "mistral.mixtral-8x7b-instruct-v0:1",
            "OpenAI GPT 3.5": "gpt-3.5-turbo",
            "OpenAI GPT 4": "gpt-4-turbo"
        }

    if provider == "Amazon Bedrock":
        # Model dropdown
        model_options = [
            "Claude 3 Sonnet",
            "Claude 3 Haiku",
            "Llama 3",
            "Amazon Titan G1 Express",
            "Mixtral 8x7B Instruct",
        ]
    elif provider == "Azure & OpenAI":
        # Model dropdown
        model_options = ["OpenAI GPT 3.5", "OpenAI GPT 4"]

    selected_model = st.session_state.model_selection = st.selectbox(
            "Select Model",
            options=model_options,
        )

    st.session_state.model_id = model_map[selected_model]

    # Quota limit
    if has_quota():
        st.subheader(f"Response received")
    else:  # No quota left.
        error_message = "Quota limit exceeded"
        st.subheader(f"LLM Gateway Exception - {error_message}")

    if st.session_state.estimated_usage:
        estimated_usage_str = '{:8f}'.format(st.session_state.estimated_usage)
    else:
        estimated_usage_str = "0"
    st.write(f"""
    - Model Selected: {st.session_state.model_selection}
    - Model Id: {st.session_state.model_id}
    - User: {username}
    - Quota Plan: Daily
    - Estimated usage for this period: \$ {estimated_usage_str} / \$ {quota_limit}
    """)

    n_input_tokens = metrics["n_input_tokens"]
    n_output_tokens = metrics["n_output_tokens"]
    input_cost = metrics["input_cost"]
    output_cost = metrics["output_cost"]

    st.write(f"""
    ##### Input metrics:
    - n_tokens: {n_input_tokens}
    - cost: $ {input_cost}
    """)

    st.write(f"""
    ##### Output metrics:
    - n_tokens: {n_output_tokens}
    - cost: $ {output_cost}
    """)

    st.write(f"""
    ##### Combined I/O metrics:
    - n_tokens: {n_output_tokens + n_input_tokens}
    - cost: $ {float(output_cost) + float(input_cost)}
    """)

