import streamlit as st
import os
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import json
import time

ApiKeyURL = os.environ["ApiKeyURL"] + "apikey"
print(f'ApiKeyURL: {ApiKeyURL}')
headers = {}
def process_access_token():
    headers = _get_websocket_headers()
    print(f'headers: {headers}')
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        print(f'returning None')
        return None
    access_token = headers['X-Amzn-Oidc-Accesstoken']
    print(f'returning {access_token}')
    return access_token

# Form to create a new API key
with st.form(key='create_api_key_form'):
    api_key_name = st.text_input("API Key Name")
    submit_button = st.form_submit_button(label='Create')

    if submit_button:
        if api_key_name:
            access_token_post = process_access_token()
            headers_post = {
                "Authorization": f"Bearer {access_token_post}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            body = {'api_key_name': api_key_name}
            print(f'body post: {body}')
            print(f'headers post: {headers_post}')
            print(f'ApiKeyURL post: {ApiKeyURL}')

            post_response = requests.post(ApiKeyURL, headers=headers_post, data=json.dumps(body))
            print(f'post_response: {post_response}')
            if post_response.status_code == 200:
                st.success('API Key created successfully!')
                st.json(post_response.json())
            else:
                st.error('Failed to create API key: HTTP status code ' + str(post_response.status_code))
        else:
            st.error('Please enter a valid API Key name.')