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
        Page("pages2/model_access_status.py", "Check Model Access Status"),
        Page("pages2/model_access_management.py", "Manage Model Access"),
        Page("pages2/quota_create.py", "Create Quota Config"),
        Page("pages2/quota_status.py", "Check Quota Status"),
        Page("pages2/quota_management.py", "Manage Quotas"),
    ]
)
add_indentation()

ModelAccessURL = os.environ["ApiGatewayModelAccessURL"] + "modelaccess/summary"

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
    col1, col2 = st.columns([3, 3])
    col1.markdown("**Username**")
    col2.markdown("**Model Access List**")
    col1, col2 = st.columns([3, 3])
    for key, value in st.session_state.model_access_config.items():
        col1.write(username)
        col2.write(value)

else:
    st.write("No Model Access config to display.")