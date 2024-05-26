import streamlit as st
import os
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import json
import time

ApiKeyURL = os.environ["ApiKeyURL"] + "apikey"

def process_access_token():
    headers = _get_websocket_headers()
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        return None
    return headers['X-Amzn-Oidc-Accesstoken']

# Form to create a new API key
with st.form(key='create_api_key_form'):
    api_key_name = st.text_input("API Key Name")
    submit_button = st.form_submit_button(label='Create')

    if submit_button and api_key_name:
        access_token_post = process_access_token()
        if access_token_post:
            headers_post = {
                "Authorization": f"Bearer {access_token_post}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            body = {'api_key_name': api_key_name}
            post_response = requests.post(ApiKeyURL, headers=headers_post, data=json.dumps(body))

            if post_response.status_code == 200:
                api_key_value = post_response.json().get("api_key_value", "")
                st.success('API Key created successfully! This is your API key, copy it down as you will not be able to see it again:')
                st.text_area("API Key", api_key_value, height=100)
            else:
                st.error('Failed to create API key: HTTP status code ' + str(post_response.status_code))
        else:
            st.error('Authorization failed. No access token available.')
    elif submit_button:
        st.error('Please enter a valid API Key name.')
