import streamlit as st
import os
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import json
import time
from datetime import datetime, timedelta


ModelAccessURL = os.environ["ApiGatewayModelAccessURL"] + "modelaccess"

def process_access_token():
    headers = _get_websocket_headers()
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        return None
    return headers['X-Amzn-Oidc-Accesstoken']


# Form to create a new API key
with st.form(key='create_model_access_form'):
    username = st.text_input("username")
    model_access_list = st.multiselect("Select models to give access to", ["anthropic.claude-3-sonnet-20240229-v1:0","anthropic.claude-3-haiku-20240307-v1:0","meta.llama3-70b-instruct-v1:0","amazon.titan-text-express-v1","mistral.mixtral-8x7b-instruct-v0:1"])

    submit_button = st.form_submit_button(label='Create')

    if submit_button and username and model_access_list:
        access_token_post = process_access_token()
        if access_token_post:
            headers_post = {
                "Authorization": f"Bearer {access_token_post}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            body = {'model_access_list': ','.join(model_access_list)}
            
            params = {
                "username": username
            }

            post_response = requests.post(ModelAccessURL, headers=headers_post, data=json.dumps(body), params=params, timeout=60)

            if post_response.status_code == 200:
                model_access_map = post_response.json().get("model_access_map", "")
                username = post_response.json().get("username", "")
                st.success(f'Model access configured successfully! This is your configured model access for {username}')
                st.code(model_access_map, language='plaintext')
            else:
                response_json = post_response.json()
                message = response_json.get("message")
                st.error('Failed to configure model access: HTTP status code ' + str(post_response.status_code) + ' Error: ' + str(message))
        else:
            st.error('Authorization failed. No access token available.')
    elif submit_button:
        st.error('Please enter a valid username, and model access.')