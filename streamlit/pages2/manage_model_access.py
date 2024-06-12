import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os
from datetime import datetime, timedelta
from st_pages import Page, show_pages, Section, add_indentation, hide_pages
import json
import jwt

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

ModelAccessURL = os.environ["ApiGatewayURL"] + "modelaccess"
region = os.environ["Region"]

#map for us-east-1, us-west-2, ap-south-1, 
model_map_1 = {
            "anthropic.claude-3-haiku-20240307-v1:0": "Claude 3 Haiku",
            "anthropic.claude-3-sonnet-20240229-v1:0": "Claude 3 Sonnet",
            "meta.llama3-70b-instruct-v1:0": "Llama 3",
            "amazon.titan-text-express-v1": "Amazon Titan",
            "mistral.mixtral-8x7b-instruct-v0:1": "Mixtral 8x7B",
        }

#map for ap-southeast-2, eu-west-1, eu-west-3
model_map_2 = {
            "anthropic.claude-3-haiku-20240307-v1:0": "Claude 3 Haiku",
            "anthropic.claude-3-sonnet-20240229-v1:0": "Claude 3 Sonnet",
            "amazon.titan-text-express-v1": "Amazon Titan",
            "mistral.mixtral-8x7b-instruct-v0:1": "Mixtral 8x7B",
        }

#map for eu-central-1
model_map_3 = {
            "anthropic.claude-3-haiku-20240307-v1:0": "Claude 3 Haiku",
            "anthropic.claude-3-sonnet-20240229-v1:0": "Claude 3 Sonnet",
            "amazon.titan-text-express-v1": "Amazon Titan",
        }

region_model_map = {
    "us-east-1": model_map_1,
    "us-west-2": model_map_1,
    "ap-south-1": model_map_1,
    "ap-southeast-2": model_map_2,
    "eu-west-1": model_map_2,
    "eu-west-3": model_map_2,
    "eu-central-1": model_map_3
}

chosen_model_map = region_model_map[region]

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

no_username_string = "Could not find username. Normal if you are running locally."
if "username" in session_token:
    if "GitHub_" in session_token["username"] and "preferred_username" in session_token:
        username = session_token['preferred_username']
    else:
        username = session_token["username"]
else:
    username = no_username_string

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
        headers = {"Authorization": f"Bearer {access_token}"}
        body = {'model_access_list': ','.join(new_access_list)}
        params = {"username": username}
        
        update_response = requests.post(ModelAccessURL, headers=headers, json=body, params=params, timeout=60)
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
    current_access_list = [chosen_model_map[model] for model in st.session_state.model_access_config["model_access_list"].split(",")]
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