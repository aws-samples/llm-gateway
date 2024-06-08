import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os
from datetime import datetime, timedelta

QuotaURL = os.environ["ApiGatewayURL"] + "quota"

def process_access_token():
    headers = _get_websocket_headers()
    print(f'headers: {headers}')
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        print(f'returning None')
        return None
    access_token = headers['X-Amzn-Oidc-Accesstoken']
    print(f'returning {access_token}')
    return access_token

def fetch_quota_config(username):
    access_token = process_access_token()
    if access_token:
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        params = {
            "username": username
        }
        response = requests.get(QuotaURL, headers=headers, params=params, timeout=60)
        if response.status_code == 200:
            return response.json()
        else:
            st.error('Failed to retrieve data: HTTP status code ' + str(response.status_code))
            return None
    else:
        st.error('Access token not available.')
        return None

def delete_quota_config(username):
    access_token = process_access_token()
    headers = {
                "Authorization": f"Bearer {access_token}"
            }
    delete_response = requests.delete(QuotaURL, headers=headers, params={'username': username}, timeout=60)
    if delete_response.status_code == 200:
        # Remove the item from session state
        st.session_state.quotas = None
        st.experimental_rerun()
    else:
        st.error('Failed to delete Quota: HTTP status code ' + str(delete_response.status_code))


# Input for username
username = st.text_input("Enter a username:")

# Submit button always visible
submitted = st.button("Submit")

# Check if the button was pressed and the username field is not empty
if submitted:
    if username:
        st.session_state.quotas = fetch_quota_config(username)
    else:
        st.error("Please enter a username before submitting.")

# Display and manage API keys
if 'quotas' in st.session_state and st.session_state.quotas:
    # Define column headers outside the loop
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    col1.markdown("**Username**")
    col2.markdown("**Quota Frequency**")
    col3.markdown("**Quota Limit**")
    col4.markdown("**Action**")
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    for key, value in st.session_state.quotas.items():
        col1.write(username)
        col2.write(key)
        col3.write(value)

        if col4.button('Delete', key=username):
            delete_quota_config(username)

else:
    st.write("No Quotas to display.")