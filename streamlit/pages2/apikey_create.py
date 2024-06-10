import streamlit as st
import os
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import json
import time
from datetime import datetime, timedelta, timezone
from st_pages import Page, show_pages, Section, add_indentation, hide_pages
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

ApiKeyURL = os.environ["ApiGatewayURL"] + "apikey"

def process_access_token():
    headers = _get_websocket_headers()
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        return None
    return headers['X-Amzn-Oidc-Accesstoken']

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
    print(f'Username {username} is not an admin. Hiding admin pages.')
    hide_pages(["Admin Pages", "Manage Model Access", "Manage Quotas", "Check Quota Status"])

# Calculate expiration timestamp based on selection
def calculate_expiration(duration):
    if duration == "1 minute":
        return (datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp()
    elif duration == '1 month':
        return (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
    elif duration == '6 months':
        return (datetime.now(timezone.utc) + timedelta(days=180)).timestamp()
    elif duration == '1 year':
        return (datetime.now(timezone.utc) + timedelta(days=365)).timestamp()
    else:
        return None

# Form to create a new API key
with st.form(key='create_api_key_form'):
    api_key_name = st.text_input("API Key Name")
    expiration_choice = st.selectbox("Select expiration duration", ["1 minute", "1 month", "6 months", "1 year", "No expiration"])
    submit_button = st.form_submit_button(label='Create')

    if submit_button and api_key_name:
        access_token_post = process_access_token()
        if access_token_post:
            headers_post = {
                "Authorization": f"Bearer {access_token_post}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            expiration_timestamp = calculate_expiration(expiration_choice)
            body = {'api_key_name': api_key_name}
            if expiration_timestamp:
                body['expiration_timestamp'] = str(expiration_timestamp)

            post_response = requests.post(ApiKeyURL, headers=headers_post, data=json.dumps(body), timeout=60)

            if post_response.status_code == 200:
                api_key_value = post_response.json().get("api_key_value", "")
                st.success('API Key created successfully! This is your API key, copy it down as you will not be able to see it again:')
                st.code(api_key_value, language='plaintext')
            else:
                response_json = post_response.json()
                message = response_json.get("message")
                st.error('Failed to create API key: HTTP status code ' + str(post_response.status_code) + ' Error: ' + str(message))
        else:
            st.error('Authorization failed. No access token available.')
    elif submit_button:
        st.error('Please enter a valid API Key name.')
