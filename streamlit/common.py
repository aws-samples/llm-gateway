
no_username_string = "Could not find username. Normal if you are running locally."

def get_username(session_token):
    if "email" in session_token:
        username = session_token['email']
    elif "preferred_username" in session_token:
        username = session_token['preferred_username']
    elif "username" in session_token:
        username = session_token["username"]
    else:
        username = no_username_string
    
    return username