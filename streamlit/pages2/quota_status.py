import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import requests
import os
from datetime import datetime, timedelta
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

QuotaURL = os.environ["ApiGatewayURL"] + "quota" + "/summary"

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

# Input for username
selected_username = st.text_input("Enter a username:")

# Submit button always visible
submitted = st.button("Submit")

# Check if the button was pressed and the username field is not empty
if submitted:
    if selected_username:
        st.session_state.quotas = fetch_quota_summary(selected_username)
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