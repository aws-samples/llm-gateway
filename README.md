# AWS LLM Gateway

Project ACTIVE as of Apr 2, 2024

## Project Overview

This project provides sample code and CDK for deploying APIs which provide a secure and scalable interface with Amazon Bedrock.

This project allows users to deploy either a standard REST API, *or* a WebSocket API which supports streaming responses from Amazon Bedrock.

The difference between these 2 options is discussed in more detail below.

## Demo

This demo video shows an LLM chatbot powered by the AWS LLM Gateway and Bedrock Streaming. 
The chatbot in this demo helps mobile network technicians summarize information about network outages, using data fetched from a (No)SQL or vector database.

![Demo of Bedrock Streaming](./media/streaming_demo.gif)

## How to deploy the backend

### REST API

1. `cd` into `lambda/rest/`
2. Deploy your image to Elastic Container Repository (ECR) by choosing a name for your ECR repository, and then following the
   instructions provided in the ECR console. The commands you'll need to run
   look something like this:
   ```
   > export AWS_REGION=<your_preferred_region>
   > export AWS_ACCOUNT_ID=<your_account_id>
   > export ECR_REPO_NAME=<your_perferred_name>
   > source create_bedrock_runtime.sh
   > aws ecr create-repository --repository-name ${ECR_REPO_NAME}
   > docker build -t ${ECR_REPO_NAME} .
   > docker tag ${ECR_REPO_NAME}:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:latest
   > aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
   > docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:latest
   ```
3. Run the following commands:
   ```
   > cd <project_root>/cdk/  # Go to the CDK directory.
   > cp template.env .env    # Create your own .env file with all necessary parameters.
   ```
4. (Optional) If you want to use non-default settings for your project, edit the settings in your `.env` file. 
   You will need to at least need to set `ECR_REST_REPOSITORY` to the name that you chose for your repository in step # 2.
5. Run `export $(cat .env | xargs)` to export your `.env` file so that your settings can be read when you deploy your CDK stack.
6. Deploy the `LlmGatewayStack` stack inside CDK (`cdk deploy`).
7. If you need to make adjustments to your lambda code, re-run step (2) to
   deploy your docker image, and then manually edit the lambda to point to your
   ECR repository's new `*:latest` tag.

### WebSocket API

1. `cd` into `lambda/ws/`
2. Deploy your image to Elastic Container Repository (ECR) by choosing a name for your ECR repository, and then following the
   instructions provided in the ECR console. The commands you'll need to run
   look something like this:
   ```
   > export AWS_REGION=<your_preferred_region>
   > export AWS_ACCOUNT_ID=<your_account_id>
   > export ECR_REPO_NAME=<your_perferred_name>
   > source create_bedrock_runtime.sh
   > aws ecr create-repository --repository-name ${ECR_REPO_NAME}
   > docker build -t ${ECR_REPO_NAME} .
   > docker tag ${ECR_REPO_NAME}:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:latest
   > aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
   > docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:latest
   ```
3. Run the following commands:
   ```
   > cd <project_root>/cdk/  # Go to the CDK directory.
   > cp template.env .env    # Create your own .env file with all necessary parameters.
   ```
4. (Optional) If you want to use non-default settings for your project, edit the settings in your `.env` file. 
   You will need to at least need to set `ECR_WEBSOCKET_REPOSITORY` to the name that you chose for your repository in step # 2.
5. Run `export $(cat .env | xargs)` to export your `.env` file so that your settings can be read when you deploy your CDK stack.
6. Deploy the `LlmGatewayStack` stack inside CDK (`cdk deploy`).
7. If you need to make adjustments to your lambda code, re-run step (2) to
   deploy your docker image, and then manually edit the lambda to point to your
   ECR repository's new `*:latest` tag.

### Deployment settings

The following are settings which you can configure as needed for your project, along with the values they can take.

This information can also be found inside `<project_root>/cdk/template.env`.

```
API_GATEWAY_TYPE="rest"          # "rest" or "websocket"
API_GATEWAY_USE_API_KEY="true"   # "true" or "false"
API_GATEWAY_USE_IAM_AUTH="true"  # "true" or "false"
DEFAULT_MAX_TOKENS="4096"
DEFAULT_TEMP="4096"
ECR_REST_REPOSITORY="llm-gateway-rest"
ECR_WEBSOCKET_REPOSITORY="llm-gateway-ws"
REGION_ID="us-east-1"
# OPENSEARCH_DOMAIN_ENDPOINT=""  # Optional
```

## Uploading data for cached question-answer pairs

The LLM Gateway has the ability to immediately respond to questions which have been asked before, by using a cache of question-answer pairs which have been asked before.

This causes a significant reduction in latency for prompts which are sent to the API, and for which that prompt appears in the cache of question-answer pairs.

You can pre-populate this cache by bulk-uploading data to your DynamoDB index.

To do this:
1. Prepare a JSON file with all the data that you want to upload to DynamoDB.
    Each data item should be its own JSON object within a top-level JSON list.
    For example, your `.json` file should look as follows:
    ```
    [
        { pk: pk1, key1: value1, ... },
        { pk: pk2, key1: value1, ... },
        { pk: pk3, key1: value1, ... },
        ...
    ]
    ```
2. Run the script from the project root directory as follows. Please remember that you should have your AWS credentials working from your command line in order for this script to work. You may need to log in or provide environment variables.
```
python scripts/bulk_upload_JSON_to_DDB/bulk_upload_JSON_to_DDB.py <path_to_JSON_file> -t <table_name>
```

For more information, please run this command from the project root directory:
```
python scripts/bulk_upload_JSON_to_DDB/bulk_upload_JSON_to_DDB.py
```

## REST or WebSockets? What's the difference?

In general, users may find the faster response time and lack of timeouts which apply to a WebSocket API to be helpful than the benefits of a REST API. This means that human interfaces with the WebSocket API will be able to gradually present the AI assistant's response to a user in chunks. This will allow a user to start reading sooner, and understand if their question was successfully answered, and if it's being answered correctly. 

This may also make WebSocket APIs faster for developers to test, compared to a REST API.

However, it is important to note that as of 2023-Nov-27, WebSocket API Gateways don't support WAF integrations, Resource Policies, or VPC links.

| Feature                                                                      | REST                 | WebSockets |
| ---------------------------------------------------------------------------- |--------------------- | ---------- |
| Stream responses from the AI assistant in chunks                             | ❌ NO                | ✅ YES     |
| User can find out if the request failed before reaching the timeout?         | ❌ NO                | ✅ YES     |
| Users can cancel requests without waiting for a full response?<sup>[0]</sup> | ❌ NO                | ✅ YES     |
| Timeout (without API Gateway)                                                | 15 min               | 15 min     |
| Timeout (with API Gateway)                                                   | 30 s                 | 10 min     |
| API Gateway supports WAF                                                     | ✅ YES               | ❌ NO      |
| API Gateway supports Resource Policies                                       | ✅ YES               | ❌ NO      |
| API Gateway supports VPC links                                               | ✅ YES               | ❌ NO      |
| ---------------------------------------------------------------------------- | -------------------- | ---------- |
| Latency metric<sup>[1]</sup>                                                 | REST                 | WebSockets |
| ---------------------------------------------------------------------------- | -------------------- | ---------- |
| Anthropic Claude with 10,000 tokens                                          | 20 s                 | 3 s        |
| Anthropic Claude with 50,000 tokens                                          | > 30 s<sup>[2]</sup> | 5 s        |

<sup>[0]</sup> Not yet implemented in this project.

<sup>[1]</sup> Defined as "the time between when a user submits a request, and when they first receive a response from the API"

<sup>[2]</sup> Exceeds the REST API Gateway timeout of 30 seconds.


## Security
See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License
This library is licensed under the MIT-0 License. See the LICENSE file.
