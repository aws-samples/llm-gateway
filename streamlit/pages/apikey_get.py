import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os
from datetime import datetime, timedelta, timezone

ApiKeyURL = os.environ["ApiGatewayURL"] + "apikey"

def process_access_token():
    headers = _get_websocket_headers()
    print(f'headers: {headers}')
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        print(f'returning None')
        return None
    access_token = headers['X-Amzn-Oidc-Accesstoken']
    print(f'returning {access_token}')
    return access_token

def get_current_timestamp():
    return (datetime.now(timezone.utc)).timestamp()

def is_expired(item):
    if 'expiration_timestamp' in item and item['expiration_timestamp']:
        current_timestamp = get_current_timestamp()
        return datetime.fromtimestamp(float(item['expiration_timestamp'])) < datetime.fromtimestamp(current_timestamp)
    return False  # Default to not expired if expiration_timestamp is missing

def format_expiration_date(item):
    if 'expiration_timestamp' in item and item['expiration_timestamp']:
        return datetime.fromtimestamp(float(item['expiration_timestamp'])).strftime('%Y-%m-%d %H:%M:%S')
    return "No Expiration Date"  # Default display when expiration_timestamp is missing

def fetch_api_keys():
    access_token = process_access_token()
    if access_token:
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        response = requests.get(ApiKeyURL, headers=headers, timeout=60)
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
    delete_response = requests.delete(ApiKeyURL, headers=headers, params={'api_key_name': item['api_key_name']}, timeout=60)
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
    # Define column headers outside the loop
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    col1.markdown("**Api Key Name**")
    col2.markdown("**Status**")
    col3.markdown("**Expiration Date**")
    col4.markdown("**Action**")

    for item in list(st.session_state.api_keys):
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        col1.write(f"{item['api_key_name']}")

        expiration_status = "expired" if is_expired(item) else "valid"
        expiration_date = format_expiration_date(item)

        col2.write(expiration_status)
        col3.write(expiration_date)

        if col4.button('Delete', key=item['api_key_name']):
            delete_api_key(item)

else:
    st.write("No API Keys to display.")