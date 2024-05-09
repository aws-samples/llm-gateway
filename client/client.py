import streamlit as st
from invoke_llm_with_streaming import llm_answer_streaming
import asyncio
import threading
import queue
import websockets

uri = "wss://8b9ldf1092.execute-api.us-east-1.amazonaws.com/prod"

st.set_page_config(layout="wide")

estimated_usage = 0
quota_limit = 0.0001

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

COST_DB = "../data/cost_db.csv"

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

with main_column:
    # Title displayed on the streamlit web app
    st.title(f""":rainbow[LLM Gateway API Sample]""")
    # configuring values for session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    # writing the message that is stored in session state
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # evaluating st.chat_input and determining if a prompt has been input
    if prompt := st.chat_input("Ask me about anything...and I will STREAM the answer!"):
        # with the user icon, write the prompt to the front end
        with st.chat_message("user"):
            st.markdown(prompt)
        # append the prompt and the role (user) as a message to the session state
        st.session_state.messages.append({"role": "user", "content": prompt})
        # respond as the assistant with the answer
        with st.chat_message("assistant"):
            q = queue.Queue()

            # Update the input metrics.
            update_metrics(prompt, "input")

            # Start the background thread

            thread = threading.Thread(
                target=bridge, args=(llm_answer_streaming(prompt), q)
            )
            thread.start()
            # making sure there are no messages present when generating the answer
            message_placeholder = st.empty()
            # calling the invoke_llm_with_streaming to generate the answer as a generator object, and using
            # st.write stream to perform the actual streaming of the answer to the front end
            answer = st.write_stream(sync_generator(q))

        # appending the final answer to the session state
        update_metrics(answer, "output")
        estimated_usage += metrics["input_cost"]
        estimated_usage += metrics["output_cost"]
        st.session_state.messages.append({"role": "assistant", "content": answer})

with right_column:
    st.header("Usage Statistics")
    # Your usage statistics functionality goes here

    user_options = ["Michael Rodriguez's User", "Andrew Young's Amazing App", "Osman Santos's Amazing App"]
    selected_user = st.selectbox("User", user_options)

    provider_options = ["Amazon Bedrock", "Azure & OpenAI"]
    provider = st.selectbox("Provider", provider_options)

    if provider == "Amazon Bedrock":
        # Model dropdown
        model_options = ["Claude 3 Sonnet", "Claude 3 Haiku", "Llama 3", "Amazon Titan"]
        selected_model = st.selectbox("Model", model_options)
    elif provider == "Azure & OpenAI":
        # Model dropdown
        model_options = ["OpenAI GPT 3.5", "OpenAI GPT 4"]
        selected_model = st.selectbox("Model", model_options)

    # Quota limit
    if estimated_usage > quota_limit:
        error_message = "Quota limit exceeded"
        st.subheader(f"LLM Gateway Exception - {error_message}")
    else:
        st.subheader(f"LLM Gateway Exception - {error_message}")

    st.write(f"""
    - Model ID: {selected_model}
    - User: {selected_user}
    - Quota Plan: Daily
    - Estimated usage for this period: {str(estimated_usage)[:7]} / {quota_limit} USD
    """)

    n_input_tokens = metrics["n_input_tokens"]
    n_output_tokens = metrics["n_output_tokens"]
    input_cost = metrics["input_cost"]
    output_cost = metrics["output_cost"]

    st.write(f"""
    ##### Input metrics:
    - n_tokens: {n_input_tokens}
    - cost: {input_cost} USD
    """)

    st.write(f"""
    ##### Output metrics:
    - n_tokens: {n_output_tokens}
    - cost: {output_cost} USD
    """)

    st.write(f"""
    ##### Combined I/O metrics:
    - n_tokens: {n_output_tokens + n_input_tokens} USD
    - cost: {float(output_cost) + float(input_cost)} USD
    """)

