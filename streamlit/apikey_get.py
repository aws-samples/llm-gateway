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

def fetch_api_keys():
    access_token = process_access_token()
    if access_token:
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        response = requests.get(ApiKeyURL, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            st.error('Failed to retrieve data: HTTP status code ' + str(response.status_code))
            return None
    else:
        st.error('Access token not available.')
        return None

def delete_api_key(item):
    access_token = process_access_token()
    headers = {
                "Authorization": f"Bearer {access_token}"
            }
    delete_response = requests.delete(ApiKeyURL, headers=headers, params={'api_key_id': item['api_key_id']})
    if delete_response.status_code == 200:
        # Remove the item from session state
        st.session_state.api_keys.remove(item)
        st.experimental_rerun()
    else:
        st.error('Failed to delete API Key: HTTP status code ' + str(delete_response.status_code))

# Initialize or update the session state
if st.button("Refresh API Keys") or 'api_keys' not in st.session_state:
    st.session_state.api_keys = fetch_api_keys()

# Display and manage API keys
if st.session_state.api_keys:
    for item in list(st.session_state.api_keys):  # Iterate over a copy to modify the list during iteration
        col1, col2 = st.columns([4, 1])
        col1.write(f"{item['api_key_name']}")
        if col2.button('Delete', key=item['api_key_id']):
            delete_api_key(item)
else:
    st.write("No API Keys to display.")
