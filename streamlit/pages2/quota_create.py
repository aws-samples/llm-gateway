import streamlit as st
import os
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import json
import time
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


QuotaURL = os.environ["ApiGatewayURL"] + "quota"

def process_access_token():
    headers = _get_websocket_headers()
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        return None
    return headers['X-Amzn-Oidc-Accesstoken']


# Form to create a new API key
with st.form(key='create_api_key_form'):
    username = st.text_input("username")
    frequency_choice = st.selectbox("Select quota frequency", ["weekly"])
    quota_limit = st.number_input('Enter the quota limit in dollars:', step=1.0)

    submit_button = st.form_submit_button(label='Create')

    if submit_button and username and frequency_choice and quota_limit:
        access_token_post = process_access_token()
        if access_token_post:
            headers_post = {
                "Authorization": f"Bearer {access_token_post}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            body = {frequency_choice: quota_limit}
            
            params = {
                "username": username
            }

            post_response = requests.post(QuotaURL, headers=headers_post, data=json.dumps(body), params=params, timeout=60)

            if post_response.status_code == 200:
                quota_map = post_response.json().get("quota_map", "")
                username = post_response.json().get("username", "")
                st.success(f'Quota created successfully! This is your configured quota for {username}')
                st.code(quota_map, language='plaintext')
            else:
                response_json = post_response.json()
                message = response_json.get("message")
                st.error('Failed to create Quota: HTTP status code ' + str(post_response.status_code) + ' Error: ' + str(message))
        else:
            st.error('Authorization failed. No access token available.')
    elif submit_button:
        st.error('Please enter a valid username, quota frequency, and quota limit.')