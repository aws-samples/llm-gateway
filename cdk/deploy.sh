#!/bin/bash

# Set the CDK stack name
STACK_NAME="LlmGatewayStack"
AWS_REGION=$(aws configure get region)
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)

PYTHON_SCRIPT="generate_salt.py"

# Check if the salt file exists
if [ ! -f salt.txt ]; then
    # Run the Python script to generate the salt file
    python3 $PYTHON_SCRIPT
fi

# Read the salt from the file into a variable
SALT=$(cat salt.txt)
echo "Salt: $SALT"

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

echo $ECR_LLM_GATEWAY_REPOSITORY
echo $API_GATEWAY_TYPE
cd ../lambdas/gateway
./build_and_deploy.sh $ECR_LLM_GATEWAY_REPOSITORY $API_GATEWAY_TYPE

#navigate back to the original directory
cd -

cd ../lambdas/api_key
./build_and_deploy.sh $ECR_API_KEY_REPOSITORY

#navigate back to the original directory
cd -

echo $UI_CERT_ARN
echo $UI_DOMAIN_NAME
echo $ECR_STREAMLIT_REPOSITORY
echo $METADATA_URL_COPIED_FROM_AZURE_AD
echo $GIT_HUB_CLIENT_ID
echo $GIT_HUB_CLIENT_SECRET
echo $GIT_HUB_PROXY_URL
echo $COGNTIO_DOMAIN_PREFIX
echo $OPENAI_API_KEY
echo $GOOGLE_API_KEY
echo $ANTHROPIC_API_KEY
echo $AZURE_OPENAI_ENDPOINT
echo $AZURE_OPENAI_API_KEY
echo $AZURE_OPENAI_API_VERSION
echo $ECR_API_KEY_REPOSITORY
echo $ECR_LLM_GATEWAY_REPOSITORY
cd ../streamlit
./build_and_deploy.sh $ECR_STREAMLIT_REPOSITORY

#navigate back to the original directory
cd -

cd lib/authorizers/websocket
npm install

#navigate back to the original directory
cd -

# Deploy the CDK stack
echo "Deploying the CDK stack..."
cdk deploy "$STACK_NAME" \
--context architecture=$ARCH \
--context apiGatewayType=$API_GATEWAY_TYPE \
--context useApiKey=$API_GATEWAY_USE_API_KEY \
--context useIamAuth=$API_GATEWAY_USE_IAM_AUTH \
--context maxTokens=$DEFAULT_MAX_TOKENS \
--context defaultTemp=$DEFAULT_TEMP \
--context ecrStreamlitRepository=$ECR_STREAMLIT_REPOSITORY \
--context uiCertArn=$UI_CERT_ARN \
--context uiDomainName=$UI_DOMAIN_NAME \
--context metadataURLCopiedFromAzureAD=$METADATA_URL_COPIED_FROM_AZURE_AD \
--context gitHubClientId=$GIT_HUB_CLIENT_ID \
--context gitHubClientSecret=$GIT_HUB_CLIENT_SECRET \
--context gitHubProxyUrl=$GIT_HUB_PROXY_URL \
--context cognitoDomainPrefix=$COGNTIO_DOMAIN_PREFIX \
--context openaiApiKey=$OPENAI_API_KEY \
--context googleApiKey=$GOOGLE_API_KEY \
--context anthropicApiKey=$ANTHROPIC_API_KEY \
--context azureOpenaiEndpoint=$AZURE_OPENAI_ENDPOINT \
--context azureOpenaiApiKey=$AZURE_OPENAI_API_KEY \
--context azureOpenaiApiVersion=$AZURE_OPENAI_API_VERSION \
--context apiKeyEcrRepoName=$ECR_API_KEY_REPOSITORY \
--context llmGatewayRepoName=$ECR_LLM_GATEWAY_REPOSITORY \
--context salt=$SALT \
--outputs-file ./outputs.json

# Check if the deployment was successful
if [ $? -eq 0 ]; then
    echo "Deployment successful. Extracting outputs..."

    # Extract outputs using the stack name variable
    USER_POOL_ID=$(jq -r ".\"${STACK_NAME}\".UserPoolId" ./outputs.json)
    USER_POOL_CLIENT_ID=$(jq -r ".\"${STACK_NAME}\".UserPoolClientId" ./outputs.json)
    WEBSOCKET_URL=$(jq -r ".\"${STACK_NAME}\".WebSocketUrl" ./outputs.json)
    API_KEY_LAMBDA_FUNCTION_NAME=$(jq -r ".\"${STACK_NAME}\".ApiKeyLambdaFunctionName" ./outputs.json)
    LLM_GATEWAY_LAMBDA_FUNCTION=$(jq -r ".\"${STACK_NAME}\".LlmgatewayLambdaFunctionName" ./outputs.json)

    # Write outputs to a file with modified keys and format
    echo "UserPoolID=$USER_POOL_ID" > resources.txt
    echo "UserPoolClientID=$USER_POOL_CLIENT_ID" >> resources.txt
    echo "WebSocketURL=$WEBSOCKET_URL" >> resources.txt
    echo "ApiKeyLambdaFunctionName=$API_KEY_LAMBDA_FUNCTION_NAME" >> resources.txt
    echo "LlmgatewayLambdaFunctionName=$LLM_GATEWAY_LAMBDA_FUNCTION" >> resources.txt

    echo "Outputs have been written to resources.txt"

    aws lambda update-function-code \
        --function-name $LLM_GATEWAY_LAMBDA_FUNCTION \
        --image-uri $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_LLM_GATEWAY_REPOSITORY:latest \
        --region $AWS_REGION
    
    aws lambda update-function-code \
        --function-name $API_KEY_LAMBDA_FUNCTION_NAME \
        --image-uri $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_API_KEY_REPOSITORY:latest \
        --region $AWS_REGION

    aws ecs update-service \
        --cluster LlmGatewayUI \
        --service LlmGatewayUI \
        --force-new-deployment \
        --desired-count 1
else
    echo "Deployment failed"
fi
