import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os
from datetime import datetime, timedelta

QuotaURL = os.environ["ApiGatewayURL"] + "quota" + "/summary"

def process_access_token():
    headers = _get_websocket_headers()
    print(f'headers: {headers}')
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        print(f'returning None')
        return None
    access_token = headers['X-Amzn-Oidc-Accesstoken']
    print(f'returning {access_token}')
    return access_token

def fetch_quota_summary(username):
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

def get_quota_status(total_estimated_cost, limit):
    if float(total_estimated_cost) > float(limit):
        return "Quota exceeded"
    return "Within Quota Limits"

# Input for username
username = st.text_input("Enter a username:")

# Submit button always visible
submitted = st.button("Submit")

# Check if the button was pressed and the username field is not empty
if submitted:
    if username:
        st.session_state.quotas = fetch_quota_summary(username)
    else:
        st.error("Please enter a username before submitting.")

# Display and manage API keys
if 'quotas' in st.session_state and st.session_state.quotas:
    # Define column headers outside the loop
    col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
    col1.markdown("**Username**")
    col2.markdown("**Quota Frequency**")
    col3.markdown("**Quota Used**")
    col4.markdown("**Quota Limit**")
    col5.markdown("**Quota Status**")

    for item in list(st.session_state.quotas):
        col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
        col1.write(f"{item['username']}")

        total_estimated_cost = item['total_estimated_cost']
        limit = item['limit']

        col2.write(item['frequency'])
        col3.write(total_estimated_cost)
        col4.write(limit)
        col5.write(get_quota_status(total_estimated_cost, limit))

else:
    st.write("No Quotas to display.")