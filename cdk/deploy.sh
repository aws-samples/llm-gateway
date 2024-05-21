#!/bin/bash

# Set the CDK stack name
STACK_NAME="LlmGatewayStack"

# Deploy the CDK stack
echo "Deploying the CDK stack..."
cdk deploy "$STACK_NAME" --outputs-file ./outputs.json

# Check if the deployment was successful
if [ $? -eq 0 ]; then
    echo "Deployment successful. Extracting outputs..."

    # Extract outputs using the stack name variable
    USER_POOL_ID=$(jq -r ".\"${STACK_NAME}\".UserPoolId" ./outputs.json)
    USER_POOL_CLIENT_ID=$(jq -r ".\"${STACK_NAME}\".UserPoolClientId" ./outputs.json)
    WEBSOCKET_URL=$(jq -r ".\"${STACK_NAME}\".WebSocketUrl" ./outputs.json)

    # Write outputs to a file with modified keys and format
    echo "UserPoolID=$USER_POOL_ID" > resources.txt
    echo "UserPoolClientID=$USER_POOL_CLIENT_ID" >> resources.txt
    echo "WebSocketURL=$WEBSOCKET_URL" >> resources.txt

    echo "Outputs have been written to resources.txt"
else
    echo "Deployment failed"
fi
