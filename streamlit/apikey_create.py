import streamlit as st
import os
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import json
import time
from datetime import datetime, timedelta

ApiKeyURL = os.environ["ApiKeyURL"] + "apikey"

def process_access_token():
    headers = _get_websocket_headers()
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        return None
    return headers['X-Amzn-Oidc-Accesstoken']

# Calculate expiration timestamp based on selection
def calculate_expiration(duration):
    if duration == "1 minute":
        return (datetime.now() + timedelta(minutes=1)).timestamp()
    elif duration == '1 month':
        return (datetime.now() + timedelta(days=30)).timestamp()
    elif duration == '6 months':
        return (datetime.now() + timedelta(days=180)).timestamp()
    elif duration == '1 year':
        return (datetime.now() + timedelta(days=365)).timestamp()
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

            post_response = requests.post(ApiKeyURL, headers=headers_post, data=json.dumps(body))

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
