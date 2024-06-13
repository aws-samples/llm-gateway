#!/bin/bash

if [ $# -ne 1 ]; then
  echo "Usage: $0 <APP_NAME>"
  exit 1
fi

APP_NAME=$1

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

echo "Copying common folder into current folder"

cp -r ../common .

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
docker build --platform $ARCH -t $APP_NAME .
docker tag $APP_NAME\:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP_NAME\:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP_NAME\:latest