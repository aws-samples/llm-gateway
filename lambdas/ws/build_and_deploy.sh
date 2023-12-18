#!/bin/bash

if [ $# -ne 2 ]; then
  echo "Usage: $0 <APP_NAME> <AWS_REGION>"
  exit 1
fi

APP_NAME=$1
AWS_REGION=$2

export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)

aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
docker build -t $APP_NAME .
docker tag $APP_NAME\:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP_NAME\:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP_NAME\:latest
