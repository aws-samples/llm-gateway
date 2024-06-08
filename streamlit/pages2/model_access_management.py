import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os
from datetime import datetime, timedelta
from st_pages import Page, show_pages, Section, add_indentation


show_pages(
    [
        Section(name="Developer Pages", icon="👨🏻‍💻"),
        Page("app.py", "Main Chat App"),
        Page("pages2/apikey_create.py", "Create API Keys"),
        Page("pages2/apikey_get.py", "Manage API Keys"),
        Section(name="Admin Pages", icon="👑"),
        Page("pages2/model_access_create.py", "Create Model Access Config"),
        Page("pages2/model_access_management.py", "Manage Model Access"),
        Page("pages2/quota_create.py", "Create Quota Config"),
        Page("pages2/quota_status.py", "Check Quota Status"),
        Page("pages2/quota_management.py", "Manage Quotas"),
    ]
)
add_indentation()

ModelAccessURL = os.environ["ApiGatewayModelAccessURL"] + "modelaccess"

model_map = {
            "anthropic.claude-3-haiku-20240307-v1:0": "Claude 3 Haiku Bedrock",
            "anthropic.claude-3-sonnet-20240229-v1:0": "Claude 3 Sonnet Bedrock",
            "meta.llama3-70b-instruct-v1:0": "Llama 3 Bedrock",
            "amazon.titan-text-express-v1": "Amazon Titan G1 Express",
            "mistral.mixtral-8x7b-instruct-v0:1": "Mixtral 8x7B Instruct Bedrock",
            "Mixtral 8x7B Instruct Bedrock": "mistral.mixtral-8x7b-instruct-v0:1",
        }

def process_access_token():
    headers = _get_websocket_headers()
    print(f'headers: {headers}')
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        print(f'returning None')
        return None
    access_token = headers['X-Amzn-Oidc-Accesstoken']
    print(f'returning {access_token}')
    return access_token

def fetch_model_access_config(username):
    access_token = process_access_token()
    if access_token:
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        params = {
            "username": username
        }
        response = requests.get(ModelAccessURL, headers=headers, params=params, timeout=60)
        if response.status_code == 200:
            return response.json()
        else:
            st.error('Failed to retrieve data: HTTP status code ' + str(response.status_code))
            return None
    else:
        st.error('Access token not available.')
        return None

def delete_model_access_config(username):
    access_token = process_access_token()
    headers = {
                "Authorization": f"Bearer {access_token}"
            }
    delete_response = requests.delete(ModelAccessURL, headers=headers, params={'username': username}, timeout=60)
    if delete_response.status_code == 200:
        # Remove the item from session state
        st.session_state.model_access_config = None
        st.experimental_rerun()
    else:
        st.error('Failed to delete Model Access Config: HTTP status code ' + str(delete_response.status_code))

def build_human_readable_model_list(model_access_list):
    human_string = ""
    for model in model_access_list.split(","):
        if human_string == "":
            human_string += model_map[model]
        else:
            human_string += ", " + model_map[model]
    print(f'human_string: {human_string}')
    return human_string

# Input for username
username = st.text_input("Enter a username:")

# Submit button always visible
submitted = st.button("Submit")

# Check if the button was pressed and the username field is not empty
if submitted:
    if username:
        st.session_state.model_access_config = fetch_model_access_config(username)
    else:
        st.error("Please enter a username before submitting.")

# Display and manage API keys
if 'model_access_config' in st.session_state and st.session_state.model_access_config:
    # Define column headers outside the loop
    col1, col2, col3, col4 = st.columns([3, 3, 1, 1])
    col1.markdown("**Username**")
    col2.markdown("**Model Access List**")
    col3.markdown("**Type**")
    col4.markdown("**Action**")

    col1, col2, col3, col4 = st.columns([3, 3, 1, 1])
    
    col1.write(username)
    human_list = build_human_readable_model_list(st.session_state.model_access_config["model_access_list"])
    print(f'human_list: {human_list}')
    col2.write(human_list)
    col3.write("Default" if st.session_state.model_access_config['default'].lower() == "true" else "Custom")

    if not st.session_state.model_access_config['default'].lower() == "true":
        if col4.button('Delete', key=username):
            delete_model_access_config(username)

else:
    st.write("No Model Access config to display.")