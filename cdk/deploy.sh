#!/bin/bash

# Set the CDK stack name
STACK_NAME="LlmGatewayStack"
AWS_REGION=$(aws configure get region)
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)

# Load environment variables from .env file
while IFS='=' read -r key value
do
    # Remove quotes around the variable values
    eval $key=$(echo $value | sed -e 's/^"//' -e 's/"$//')
done < ".env"

ARCH=$(uname -m)
case $ARCH in
    x86_64)
        ARCH="x86"
        ;;
    arm64)
        ARCH="arm"
        ;;
    *)
        echo "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

echo $ARCH

cd ../lambdas/ws
./build_and_deploy.sh $ECR_WEBSOCKET_REPOSITORY

#navigate back to the original directory
cd -

# Deploy the CDK stack
echo "Deploying the CDK stack..."
cdk deploy "$STACK_NAME" \
--context architecture=$ARCH \
--context apiGatewayType=$API_GATEWAY_TYPE \
--context apiKey=$API_KEY \
--context useApiKey=$API_GATEWAY_USE_API_KEY \
--context useIamAuth=$API_GATEWAY_USE_IAM_AUTH \
--context maxTokens=$DEFAULT_MAX_TOKENS \
--context defaultTemp=$DEFAULT_TEMP \
--context ecrWebsocketRepository=$ECR_WEBSOCKET_REPOSITORY \
--outputs-file ./outputs.json

# Check if the deployment was successful
if [ $? -eq 0 ]; then
    echo "Deployment successful. Extracting outputs..."

    # Extract outputs using the stack name variable
    USER_POOL_ID=$(jq -r ".\"${STACK_NAME}\".UserPoolId" ./outputs.json)
    USER_POOL_CLIENT_ID=$(jq -r ".\"${STACK_NAME}\".UserPoolClientId" ./outputs.json)
    WEBSOCKET_URL=$(jq -r ".\"${STACK_NAME}\".WebSocketUrl" ./outputs.json)
    WEBSOCKET_LAMBDA_FUNCTION_NAME=$(jq -r ".\"${STACK_NAME}\".WebSocketLambdaFunctionName" ./outputs.json)

    # Write outputs to a file with modified keys and format
    echo "UserPoolID=$USER_POOL_ID" > resources.txt
    echo "UserPoolClientID=$USER_POOL_CLIENT_ID" >> resources.txt
    echo "WebSocketURL=$WEBSOCKET_URL" >> resources.txt
    echo "WebSocketLambdaFunctionName=$WEBSOCKET_LAMBDA_FUNCTION_NAME" >> resources.txt

    echo "Outputs have been written to resources.txt"

    aws lambda update-function-code \
        --function-name $WEBSOCKET_LAMBDA_FUNCTION_NAME \
        --image-uri $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_WEBSOCKET_REPOSITORY:latest \
        --region $AWS_REGION
else
    echo "Deployment failed"
fi
