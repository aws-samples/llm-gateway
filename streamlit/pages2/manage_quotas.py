import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os
from datetime import datetime, timedelta
from st_pages import Page, show_pages, Section, add_indentation, hide_pages
import json
import jwt

st.set_page_config(layout="wide")

show_pages(
    [
        Section(name="Developer Pages", icon="👨🏻‍💻"),
        Page("app.py", "Main Chat App"),
        Page("pages2/apikey_create.py", "Create API Keys"),
        Page("pages2/apikey_get.py", "Manage API Keys"),
        Section(name="Admin Pages", icon="👑"),
        Page("pages2/manage_model_access.py", "Manage Model Access"),
        Page("pages2/manage_quotas.py", "Manage Quotas"),
        Page("pages2/quota_status.py", "Check Quota Status"),
    ]
)
add_indentation()

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

def process_session_token():
    '''
    WARNING: We use unsupported features of Streamlit
             However, this is quite fast and works well with
             the latest version of Streamlit (1.27)
             Also, this does not verify the session token's
             authenticity. It only decodes the token.
    '''
    headers = _get_websocket_headers()
    if not headers or "X-Amzn-Oidc-Data" not in headers:
        return {}
    return jwt.decode(
        headers["X-Amzn-Oidc-Data"], algorithms=["ES256"], options={"verify_signature": False}
    )

session_token = process_session_token()

no_username_string = "Could not find username. Normal if you are running locally."
if "username" in session_token:
    if "GitHub_" in session_token["username"] and "preferred_username" in session_token:
        username = session_token['preferred_username']
    else:
        username = session_token["username"]
else:
    username = no_username_string

admin_list = os.environ["AdminList"].split(",") if "AdminList" in os.environ  else []

if username not in admin_list and username != no_username_string:
    role = "Developer"
    print(f'Username {username} is not an admin. Hiding admin pages.')
    hide_pages(["Admin Pages", "Manage Model Access", "Manage Quotas", "Check Quota Status"])
else:
    role = "Admin"

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

def fetch_and_display_quota_config(username):
    quota_config = fetch_quota_config(username)
    if quota_config:
        st.session_state.quota_config = quota_config
    else:
        # Clear session state if fetch fails to ensure UI consistency
        if 'quota_config' in st.session_state:
            del st.session_state.quota_config

def update_quota_config(username, new_frequency, new_limit):
    access_token = process_access_token()
    if access_token:
        headers = {"Authorization": f"Bearer {access_token}"}
        body = {new_frequency: new_limit}
        params = {"username": username}
        
        update_response = requests.post(QuotaURL, headers=headers, data=json.dumps(body), params=params, timeout=60)
        if update_response.status_code == 200:
            st.success('Quota config updated successfully.')
            fetch_and_display_quota_config(username)
            st.experimental_rerun()
        else:
            st.error('Failed to update Model Access Config: HTTP status code ' + str(update_response.status_code))

def delete_quota_config(username):
    access_token = process_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    delete_response = requests.delete(QuotaURL, headers=headers, params={'username': username}, timeout=60)
    if delete_response.status_code == 200:
        st.success('Quota Config deleted successfully.')
        # Remove the item from session state
        if 'quota_config' in st.session_state:
            del st.session_state.quota_config
        fetch_and_display_quota_config(username)  # Refetch to display any remaining configurations or clear state
        st.experimental_rerun()
    else:
        st.error('Failed to delete Quota Config: HTTP status code ' + str(delete_response.status_code))

html_content = f"""
        <style>
        #MainMenu {{visibility: hidden;}}
        .css-18e3th9 {{visibility: hidden;}}
        .stApp {{padding-top: 70px;}}
        </style>
        <div style="position:absolute;top:0;right:0;padding:10px;z-index:1000">
        Logged in as: <b>{username} ({role})</b>
        </div>
        """
st.markdown(html_content, unsafe_allow_html=True)

frequency_options = ["weekly"]

# Input for username
selected_username = st.text_input("Enter a username:")

# Submit button always visible
submitted = st.button("Submit")

access_token = process_access_token()
#st.write(f'access_token: {access_token}')

# Check if the button was pressed and the username field is not empty
if submitted:
    if selected_username:
        st.session_state.selected_username = selected_username
        st.session_state.quota_config = fetch_quota_config(selected_username)
    else:
        st.error("Please enter a username before submitting.")

# Here is a slight change where the configuration fetch happens after successful update or delete
if 'quota_config' in st.session_state and st.session_state.quota_config:
    col1, col2, col3, col4, col5, col6 = st.columns([1, 1, 1, 1, 1, 1])
    col1.markdown("**Username**")
    col2.markdown("**Quota Frequency**")
    col3.markdown("**Quota Limit**")
    col4.markdown("**Type**")
    col5.markdown("**Update**")
    col6.markdown("**Action**")

    col1.write(st.session_state.selected_username)
    config = st.session_state.quota_config['quota_map']
    current_frequency = next(iter(config))
    current_limit = config[current_frequency]

    print(f'current_frequency: {current_frequency}')
    new_frequency = col2.multiselect("Edit Quota Frequency", list(frequency_options), default=[current_frequency])
    new_limit = col3.number_input('Enter the quota limit in dollars:', step=1.0, value=float(current_limit))
    col4.write("Default" if st.session_state.quota_config['default'].lower() == "true" else "Custom")

    if col5.button('Save Changes', key=f"save_{st.session_state.selected_username}"):
        update_quota_config(st.session_state.selected_username, new_frequency[0], new_limit)

    if not st.session_state.quota_config['default'].lower() == "true":
        if col6.button('Reset To Defaults', key=f"delete_{st.session_state.selected_username}"):
            delete_quota_config(st.session_state.selected_username)

else:
    st.write("No Quota config to display.")