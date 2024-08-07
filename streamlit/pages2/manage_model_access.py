import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os
from datetime import datetime, timedelta
from st_pages import Page, show_pages, Section, add_indentation, hide_pages
import json
import jwt
from common import get_username, no_username_string

st.set_page_config(layout="wide")

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

model_map_all_models = {
            "anthropic.claude-3-haiku-20240307-v1:0": "Claude 3 Haiku",
            "anthropic.claude-3-sonnet-20240229-v1:0": "Claude 3 Sonnet",
            "meta.llama3-70b-instruct-v1:0": "Llama 3",
            "amazon.titan-text-express-v1": "Amazon Titan",
            "mistral.mixtral-8x7b-instruct-v0:1": "Mixtral 8x7B",
            "cohere.embed-multilingual-v3":"Cohere Embed Multilingual",
            "cohere.embed-english-v3":"Cohere Embed English"
        }

ModelAccessURL = os.environ["LlmGatewayUrl"] + "/modelaccess"
region = os.environ["Region"]

chosen_model_map = {}

ENABLED_MODELS = os.environ["ENABLED_MODELS"]
enabled_models_list = ENABLED_MODELS.split(",")
for enabled_model in enabled_models_list:
    enabled_model_split = enabled_model.split("_")
    if len(enabled_model_split) == 1:
        model = enabled_model_split[0]
    else:
        model = enabled_model_split[1]
    if model in model_map_all_models:
        chosen_model_map[model] = model_map_all_models[model]

def process_access_token():
    headers = _get_websocket_headers()
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        print(f'returning None')
        return None
    access_token = headers['X-Amzn-Oidc-Accesstoken']
    return access_token

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

username = get_username(session_token)
admin_list = os.environ["AdminList"].split(",") if "AdminList" in os.environ  else []

if username not in admin_list and username != no_username_string:
    role = "Developer"
    print(f'Username {username} is not an admin. Hiding admin pages.')
    hide_pages(["Admin Pages", "Manage Model Access", "Manage Quotas", "Check Quota Status"])
else:
    role = "Admin"

def build_human_readable_model_list(model_access_list):
    human_string = ""
    for model in model_access_list.split(","):
        if model in chosen_model_map:
            if human_string == "":
                human_string += chosen_model_map[model]
            else:
                human_string += ", " + chosen_model_map[model]
    print(f'human_string: {human_string}')
    return human_string

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

def fetch_and_display_model_access(username):
    model_access_config = fetch_model_access_config(username)
    if model_access_config:
        st.session_state.model_access_config = model_access_config
    else:
        # Clear session state if fetch fails to ensure UI consistency
        if 'model_access_config' in st.session_state:
            del st.session_state.model_access_config

def update_model_access_config(username, new_access_list):
    access_token = process_access_token()
    if access_token:
        headers_post = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        body = {'model_access_list': ','.join(new_access_list)}
        params = {"username": username}
        
        update_response = requests.post(ModelAccessURL, headers=headers_post, json=body, params=params, timeout=60)
        if update_response.status_code == 200:
            st.success('Model access updated successfully.')
            fetch_and_display_model_access(username)
            st.experimental_rerun()
        else:
            st.error('Failed to update Model Access Config: HTTP status code ' + str(update_response.status_code))

def delete_model_access_config(username):
    access_token = process_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    delete_response = requests.delete(ModelAccessURL, headers=headers, params={'username': username}, timeout=60)
    if delete_response.status_code == 200:
        st.success('Model Access Config deleted successfully.')
        # Remove the item from session state
        if 'model_access_config' in st.session_state:
            del st.session_state.model_access_config
        fetch_and_display_model_access(username)  # Refetch to display any remaining configurations or clear state
        st.experimental_rerun()
    else:
        st.error('Failed to delete Model Access Config: HTTP status code ' + str(delete_response.status_code))

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

# Input for username
selected_username = st.text_input("Enter a username:")

# Submit button always visible
submitted = st.button("Submit")

access_token = process_access_token()
#st.write(f'access_token: {access_token}')

# Check if the button was pressed and the username field is not empty
if submitted:
    if selected_username:
        st.session_state.selected_username = selected_username
        st.session_state.model_access_config = fetch_model_access_config(selected_username)
    else:
        st.error("Please enter a username before submitting.")

# Here is a slight change where the configuration fetch happens after successful update or delete
if 'model_access_config' in st.session_state and st.session_state.model_access_config:
    col1, col2, col3, col4, col5 = st.columns([1, 3, 1, 1, 1])
    col1.markdown("**Username**")
    col2.markdown("**Model Access List**")
    col3.markdown("**Type**")
    col4.markdown("**Update**")
    col5.markdown("**Action**")

    col1.write(st.session_state.selected_username)
    current_access_list = [chosen_model_map[model] for model in st.session_state.model_access_config["model_access_list"].split(",")
                           if model in chosen_model_map]
    new_access_list = col2.multiselect("Edit Access List", list(chosen_model_map.values()), default=current_access_list)
    col3.write("Default" if st.session_state.model_access_config['default'].lower() == "true" else "Custom")

    if col4.button('Save Changes', key=f"save_{st.session_state.selected_username}"):
        new_access_codes = [key for key, value in chosen_model_map.items() if value in new_access_list]
        update_model_access_config(st.session_state.selected_username, new_access_codes)

    if not st.session_state.model_access_config['default'].lower() == "true":
        if col5.button('Reset To Defaults', key=f"delete_{st.session_state.selected_username}"):
            delete_model_access_config(st.session_state.selected_username)

else:
    st.write("No Model Access config to display.")