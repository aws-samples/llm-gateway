import boto3

def read_resources(file_path):
    """ Read resources from the file and return UserPoolID and UserPoolClientID """
    with open(file_path, 'r', encoding="utf-8") as file:
        content = file.read()
    
    resources = {}
    for line in content.splitlines():
        key, value = line.split('=')
        resources[key.strip()] = value.strip()
        
    return resources['UserPoolID'], resources['UserPoolClientID']

def write_resources(file_path, username, password):
    """ Append the new username and password to the resources file """
    with open(file_path, 'a', encoding="utf-8") as file:
        file.write(f"\nUsername={username}\nPassword={password}")

def create_cognito_user(user_pool_id, client_id, username, password):
    """ Create a Cognito user with the specified username and password """
    # Initialize Cognito Identity Provider client
    client = boto3.client('cognito-idp')

    try:
        # Create user with temporary password
        response = client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=username,
            TemporaryPassword=password,
            MessageAction='SUPPRESS',  # Suppresses the email
        )
        
        # Set user password permanently and mark it as not requiring change on first login
        client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=username,
            Password=password,
            Permanent=True
        )

        return response
    except Exception as e:
        print(f"An error occurred: {e}")

def main():
    user_pool_id, client_id = read_resources("../cdk/resources.txt")
    username = input("Enter username: ")
    password = input("Enter password: ")
    result = create_cognito_user(user_pool_id, client_id, username, password)
    
    if result:
        write_resources("resources.txt", username, password)
        print("User created and updated in resources file successfully.")
    else:
        print("Failed to create user.")

if __name__ == "__main__":
    main()
