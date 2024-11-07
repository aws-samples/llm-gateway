#!/bin/bash

# Run the main deployment script to create cloud infrastructure
cd cdk
. ./deploy.sh
cd ..

# Create a Cognito admin user
cd scripts
python create_cognito_user.py -u "admin" -p "Password123!"
cd ..
