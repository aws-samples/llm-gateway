import argparse
import boto3
from botocore.exceptions import BotoCoreError, ClientError

def authenticate_user(client, user_pool_id, client_id, username, password):
    try:
        # Authenticate the user and get the tokens or challenges
        response = client.admin_initiate_auth(
            UserPoolId=user_pool_id,
            ClientId=client_id,
            AuthFlow='ADMIN_NO_SRP_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password
            }
        )
        print(f'Response: {response}')

        if 'AuthenticationResult' in response:
            return response['AuthenticationResult']['AccessToken']
        elif 'ChallengeName' in response and response['ChallengeName'] == 'NEW_PASSWORD_REQUIRED':
            return response  # Returning the whole response to handle the challenge outside
        else:
            return "Unexpected response format or challenge."

    except (ClientError, BotoCoreError) as error:
        return str(error)

def respond_new_password_required(client, username, session, new_password):
    try:
        response = client.respond_to_auth_challenge(
            ClientId='7gsbshgko4m5ud6omrprkjp4e4',
            ChallengeName='NEW_PASSWORD_REQUIRED',
            Session=session,
            ChallengeResponses={
                'USERNAME': username,
                'NEW_PASSWORD': new_password
            }
        )
        print(f'Password update response: {response}')
        return response.get('AuthenticationResult', {}).get('AccessToken')
    except (ClientError, BotoCoreError) as error:
        return str(error)

def main(args):
    # AWS Cognito details
    user_pool_id = 'us-east-1_61SqKxPA1'
    client_id = '7gsbshgko4m5ud6omrprkjp4e4'

    # Initialize a Cognito Identity Provider client
    client = boto3.client('cognito-idp')

    # Authenticate the user and handle challenges
    result = authenticate_user(client, user_pool_id, client_id, args.username, args.password)
    if isinstance(result, dict) and 'ChallengeName' in result:
        # Handle NEW_PASSWORD_REQUIRED challenge
        access_token = respond_new_password_required(
            client, args.username, result['Session'], args.new_password
        )
    elif isinstance(result, str) and result.startswith('ey'):
        access_token = result
    else:
        print("Authentication failed or error occurred:", result)
        return

    if access_token and access_token.startswith('ey'):
        # If you need to perform more actions with the access token, you can do so here
        print("Authentication successful. Access Token obtained.")
    else:
        print("Failed to obtain valid access token after challenge response.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Change AWS Cognito User Password")
    parser.add_argument("username", help="Username of the user")
    parser.add_argument("password", help="Current password of the user")
    parser.add_argument("new_password", help="New password for the user")

    args = parser.parse_args()
    main(args)
