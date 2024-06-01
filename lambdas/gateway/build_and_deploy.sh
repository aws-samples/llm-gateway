#!/bin/bash

if [ $# -ne 2 ]; then
  echo "Usage: $0 <APP_NAME> <SERVERLESS_API>"
  exit 1
fi

APP_NAME=$1
SERVERLESS_API=$2
# Convert SERVERLESS_API to lowercase using tr and check if it is "true"
if [ "$(echo "$SERVERLESS_API" | tr '[:upper:]' '[:lower:]')" = "true" ]; then
  DOCKERFILE=Dockerfile
else
  DOCKERFILE=Dockerfile_ecs
fi

AWS_REGION=$(aws configure get region)
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)

# Check if the repository already exists
REPO_EXISTS=$(aws ecr describe-repositories --repository-names $APP_NAME 2>/dev/null)

if [ -z "$REPO_EXISTS" ]; then
    # Repository does not exist, create it
    aws ecr create-repository --repository-name $APP_NAME
else
    echo "Repository $APP_NAME already exists, skipping creation."
fi

ARCH=$(uname -m)
case $ARCH in
    x86_64)
        ARCH="linux/amd64"
        ;;
    arm64)
        ARCH="linux/arm64"
        ;;
    *)
        echo "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

echo $ARCH

aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
docker build --platform $ARCH -f $DOCKERFILE -t $APP_NAME .
docker tag $APP_NAME\:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP_NAME\:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP_NAME\:latest