import streamlit as st
import asyncio
import threading
import queue
import warnings
import boto3
from streamlit_float import *
from streamlit.web.server.websocket_headers import _get_websocket_headers
import jwt
from invoke_llm_with_streaming import llm_answer_streaming
from invoke_llm_with_streaming import thread_safe_session_state
import os
import requests
from st_pages import Page, show_pages, Section, add_indentation, hide_pages
from common import get_username, no_username_string

region = os.environ["Region"]
cognito_domain_prefix = os.environ["CognitoDomainPrefix"] if "CognitoDomainPrefix" in os.environ  else ""
cognito_client_id = os.environ["CognitoClientId"] if "CognitoClientId" in os.environ  else ""

st.set_page_config(layout="wide")
float_init(theme=True, include_unstable_primary=False)

show_pages(
    [
        Section(name="Developer Pages", icon="👨🏻‍💻"),
        Page("app.py", "Main Chat App"),
        Page("pages2/apikey_create.py", "Create API Keys"),
        Page("pages2/apikey_get.py", "Manage API Keys"),
        Section(name="Admin Pages", icon="👑"),
        Page("pages2/manage_model_access.py", "Manage Model Access"),
        Page("pages2/manage_quotas.py", "Manage Quotas"),
        Page("pages2/quota_status.py", "Check Quota Status"),
    ]
)
add_indentation()

# Initialize session state.
if "messages" not in st.session_state:
    st.session_state.messages = []
if "estimated_usage" not in st.session_state:
    st.session_state.estimated_usage = 0
# Inialize global variables.

quota_limit = 0.1000
is_streaming = False
QuotaURL = os.environ["LlmGatewayUrl"] + "/quota" + "/currentusersummary"
ModelAccessURL = os.environ["LlmGatewayUrl"] + "/modelaccess" + "/currentuser"

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

if 'provider_id' not in st.session_state:
    st.session_state['provider_id'] = None

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

def process_access_token():
    headers = _get_websocket_headers()
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        print(f'returning None')
        return None
    access_token = headers['X-Amzn-Oidc-Accesstoken']
    return access_token

session_token = process_session_token()
#st.write(f'session_token: {session_token}')

access_token = process_access_token()
#st.write(f'access_token: {access_token}')

#st.write(session_token)
username = get_username(session_token)

admin_list = os.environ["AdminList"].split(",") if "AdminList" in os.environ  else []
if username not in admin_list and username != no_username_string:
    role = "Developer"
    print(f'Username {username} is not an admin. Hiding admin pages.')
    hide_pages(["Admin Pages", "Manage Model Access", "Manage Quotas", "Check Quota Status"])
else:
    role = "Admin"

def initialize_model_id():
    st.session_state['model_id'] = "anthropic.claude-3-sonnet-20240229-v1:0"

def initialize_provider_id():
    st.session_state['provider_id'] = "amazon"

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
    n_tokens: str,
    use_cache:bool=False,
) -> float:
    if type_ not in ["input", "output"]:
        raise Exception("`type_` must be one of [\"input\", \"output\"]")

    key = ",".join([model, region, type_])

    cost_key = ""
    if type_ == "input":
        cost_key = "cost_per_token_input"
    elif type_ == "output":
        cost_key = "cost_per_token_output"


    if use_cache:  # Skip the DDB step for better cost / time performance
        with open(COST_DB, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            costs_dict = {}
            for row in reader:
                model_name = row["model_name"]
                region = row["region"]
                cost = float(row[cost_key])

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

    return cost_per_token * n_tokens

################################################################################
# END - Lambda code
################################################################################

def fetch_quota_summary():
    access_token = process_access_token()
    if access_token:
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        response = requests.get(QuotaURL, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json()
        else:
            st.error('Failed to retrieve data: HTTP status code ' + str(response.status_code))
            return None
    else:
        st.error('Access token not available.')
        return None

def fetch_model_access():
    access_token = process_access_token()
    if access_token:
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        response = requests.get(ModelAccessURL, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json()
        else:
            st.error('Failed to retrieve data: HTTP status code ' + str(response.status_code) + " " + str(response.json()))
            return None
    else:
        st.error('Access token not available.')
        return None

metrics = {
    "n_input_tokens": 0,
    "n_output_tokens": 0,
    "input_cost": 0,
    "output_cost": 0,
}

def format_two_significant_figures(num_str):
    num = float(num_str)
    return f"{num:.2f}"

def format_cost(num_str):
    num = float(num_str)
    return f"{num:.8f}"

quota_summary = fetch_quota_summary()[0]
metrics["total_estimated_cost"] = format_two_significant_figures(quota_summary['total_estimated_cost'])
metrics["limit"] = quota_summary['limit']
metrics['frequency'] = quota_summary['frequency']


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


def update_metrics(model, n_tokens, type_):
    print(metrics)
    #Needed for switching models and refreshes to work correctly
    if n_tokens:
        metrics[f"n_{type_}_tokens"] = n_tokens
        metrics[f"{type_}_cost"] = estimate_cost(
            model,
            region,
            type_,
            n_tokens,
            use_cache=True
        )
    else:
        metrics[f"{type_}_cost"] = 0
        metrics[f"n_{type_}_tokens"] = 0
    quota_summary = fetch_quota_summary()[0]
    metrics["total_estimated_cost"] = format_two_significant_figures(quota_summary['total_estimated_cost'])
    metrics["limit"] = quota_summary['limit']
    metrics['frequency'] = quota_summary['frequency']

    print(metrics)

def convert_frequency_to_human_readable(frequency):
    if frequency == "weekly":
        return "week"

html_content = f"""
        <style>
        #MainMenu {{visibility: hidden;}}
        .css-18e3th9 {{visibility: hidden;}}
        .stApp {{padding-top: 70px;}}
        </style>
        <div style="position:absolute;top:0;right:0;padding:10px;z-index:1000">
        Logged in as: <b>{username} ({role})</b>
        </div>
        """
st.markdown(html_content, unsafe_allow_html=True)

# Create two columns
main_column, right_column = st.columns([3, 1])
if "is_responding" not in st.session_state:
    st.session_state.is_responding = False

if "model_access" not in st.session_state:
    model_access = fetch_model_access()
    print(f'model_access: {model_access}')
    st.session_state.model_access = model_access['model_access_list']


def chat_content():
    # append the prompt and the role (user) as a message to the session state
    if "answer" in st.session_state:
        st.session_state.messages.append({"role": "assistant", "content": st.session_state.answer or "Quota limit exceeded." })
    if len(messages) == 0:
        st.session_state.messages.append({"role": "user", "content": st.session_state.prompt})
    st.session_state.is_responding = True

#Needed for switching models and refreshes to work correctly
def clear_chat_id():
    if thread_safe_session_state.get("chat_id"): 
       thread_safe_session_state.delete("chat_id")

def move_to_front(lst, value):
    if value in lst:
        lst.remove(value)
        lst.insert(0, value)
    return lst


with main_column:
    st.title(f""":rainbow[LLM Gateway]""")

    #Needed for switching models and refreshes to work correctly
    if "prompt" not in st.session_state or not st.session_state.prompt:
        st.session_state.is_responding = False
        st.session_state.messages = []
        if "answer" in st.session_state:
            del st.session_state.answer
        if thread_safe_session_state.get("chat_id"):
            thread_safe_session_state.delete("chat_id")

    if st.session_state.model_id == None:
        initialize_model_id()

    if st.session_state.provider_id == None:
        initialize_provider_id()

    if messages := st.session_state.messages:
        if len(messages) > 1:
            st.session_state.messages.append({"role": "user", "content": st.session_state.prompt})

        if len(messages) > 1:
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
                # Start the background thread
                print(f'st.session_state.model_id: {st.session_state.model_id}')
                print(f'st.session_state.provider_id: {st.session_state.provider_id}')
                thread = threading.Thread(
                    target=bridge,
                    args=(
                        llm_answer_streaming(
                            st.session_state.prompt,
                            st.session_state.model_id,
                            access_token
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
                    if thread_safe_session_state.get("prompt_tokens"):
                        update_metrics(st.session_state.model_id, thread_safe_session_state.get("prompt_tokens"), "input")
                    if thread_safe_session_state.get("completion_tokens"):
                        update_metrics(st.session_state.model_id, thread_safe_session_state.get("completion_tokens"), "output")

                    print(st.session_state.estimated_usage)
                    st.session_state.estimated_usage += metrics["input_cost"]
                    st.session_state.estimated_usage += metrics["output_cost"]

    st.chat_input("Ask me about anything...", key='prompt', on_submit=chat_content)


with right_column:

    st.header("Usage Statistics")
    # Your usage statistics functionality goes here

    #ToDo: ReAdd support for other models with OpenAI interface
    provider_options = ["Amazon Bedrock"]#, "OpenAI", "Google", "Anthropic", "Azure"]

    #Need clear_chat_id for switching models to work correctly
    selected_provider = st.session_state.provider_selection = st.selectbox("Provider", provider_options, on_change=clear_chat_id)

    model_map = {
            "Claude 3 Haiku Bedrock": "anthropic.claude-3-haiku-20240307-v1:0",
            "Claude 3 Sonnet Bedrock": "anthropic.claude-3-sonnet-20240229-v1:0",
            "Llama 3 Bedrock": "meta.llama3-70b-instruct-v1:0",
            "Amazon Titan G1 Express": "amazon.titan-text-express-v1",
            "Mixtral 8x7B Instruct Bedrock": "mistral.mixtral-8x7b-instruct-v0:1",
            "GPT 3.5 OpenAI": "gpt-3.5-turbo",
            "GPT 4 OpenAI": "gpt-4-turbo",
            "Gemini Pro Google": "gemini-pro",
            "Claude 3 Sonnet Anthropic": "claude-3-sonnet-20240229",
            "Claude 3 Haiku Anthropic": "claude-3-haiku-20240307",
            "Claude 3 Opus Anthropic": "claude-3-opus-20240229",

            #Note: Azure does not use constant model ids. Instead, you call a "Deployment" which can have any name you want. So you will need to edit all the Azure model ids to match your deployment
            "GPT 3.5 Azure": "my-gpt35"
    }
    
    bedrock_reverse_model_map = {
            "anthropic.claude-3-haiku-20240307-v1:0": "Claude 3 Haiku Bedrock",
            "anthropic.claude-3-sonnet-20240229-v1:0": "Claude 3 Sonnet Bedrock",
            "meta.llama3-70b-instruct-v1:0": "Llama 3 Bedrock",
            "amazon.titan-text-express-v1": "Amazon Titan G1 Express",
            "mistral.mixtral-8x7b-instruct-v0:1": "Mixtral 8x7B Instruct Bedrock",
        }

    provider_map = {
        "Amazon Bedrock": "amazon",
        "OpenAI": "openai",
        "Google": "google",
        "Anthropic": "anthropic",
        "Azure": "azure",
    }
    model_access_list = st.session_state.model_access.split(",")
    if selected_provider == "Amazon Bedrock":
        # Model dropdown
        model_options = []
        for model in model_access_list:
            if model in bedrock_reverse_model_map.keys():
                model_options.append(bedrock_reverse_model_map[model])

        move_to_front(model_options, "Claude 3 Haiku Bedrock")
        
    elif selected_provider == "OpenAI":
        # Model dropdown
        model_options = ["GPT 3.5 OpenAI", "GPT 4 OpenAI"]
    elif selected_provider == "Google":
        model_options = ["Gemini Pro Google"]
    elif selected_provider == "Anthropic":
        model_options = ["Claude 3 Sonnet Anthropic", "Claude 3 Haiku Anthropic", "Claude 3 Opus Anthropic"]
    elif selected_provider == "Azure":
        model_options = ["GPT 3.5 Azure"]

    #Need clear_chat_id for switching models to work correctly
    selected_model = st.session_state.model_selection = st.selectbox(
            "Select Model",
            options=model_options,
            on_change=clear_chat_id
        )

    st.session_state.model_id = model_map[selected_model]
    st.session_state.provider_id = provider_map[selected_provider]

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
    - Provider Selected: {st.session_state.provider_selection}
    - Provider Id: {st.session_state.provider_id}
    - Model Selected: {st.session_state.model_selection}
    - Model Id: {st.session_state.model_id}
    - Estimated usage for this {convert_frequency_to_human_readable(metrics['frequency'])}: \$ {metrics["total_estimated_cost"]} / \$ {metrics["limit"]}
    """)

    n_input_tokens = metrics["n_input_tokens"]
    n_output_tokens = metrics["n_output_tokens"]
    input_cost = metrics["input_cost"]
    output_cost = metrics["output_cost"]

    st.write(f"""
    ##### Input metrics:
    - n_tokens: {n_input_tokens}
    - cost: $ {format_cost(input_cost)}
    """)

    st.write(f"""
    ##### Output metrics:
    - n_tokens: {n_output_tokens}
    - cost: $ {format_cost(output_cost)}
    """)

    st.write(f"""
    ##### Combined I/O metrics:
    - n_tokens: {n_output_tokens + n_input_tokens}
    - cost: $ {format_cost(float(output_cost) + float(input_cost))}
    """)

