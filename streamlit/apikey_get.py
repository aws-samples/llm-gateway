import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os

ApiKeyURL = os.environ["ApiKeyURL"] + "apikey"

def process_access_token():
    headers = _get_websocket_headers()
    print(f'headers: {headers}')
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        print(f'returning None')
        return None
    access_token = headers['X-Amzn-Oidc-Accesstoken']
    print(f'returning {access_token}')
    return access_token

access_token = process_access_token()
if access_token:
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get(ApiKeyURL, headers=headers)
    if response.status_code == 200:
        data = response.json()
        st.json(data)
    else:
        st.error('Failed to retrieve data: HTTP status code ' + str(response.status_code))
else:
    st.error('Access token not available.')

