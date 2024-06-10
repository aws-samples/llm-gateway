import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os
from datetime import datetime, timedelta, timezone
from st_pages import Page, show_pages, Section, add_indentation, hide_pages
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

ApiKeyURL = os.environ["ApiGatewayURL"] + "apikey"

def process_access_token():
    headers = _get_websocket_headers()
    if 'X-Amzn-Oidc-Accesstoken' not in headers:
        print(f'returning None')
        return None
    access_token = headers['X-Amzn-Oidc-Accesstoken']
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