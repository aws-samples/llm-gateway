""" Copyright 2023 Amazon.com, Inc. and its affiliates. All Rights Reserved.

Licensed under the Amazon Software License (the "License").
You may not use this file except in compliance with the License.
A copy of the License is located at

  http://aws.amazon.com/asl/

or in the "license" file accompanying this file. This file is distributed
on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
express or implied. See the License for the specific language governing
permissions and limitations under the License.
"""

import argparse
import asyncio
import io
import json
import logging
import websockets
import zipfile
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


#test_prompt = """Summarize the key details of incidents and journal text as listed below. Report any outages, damages, and replacements. Detail all interventions performed. Ignore:- Technician ID and Contact: [Do not provide the ID and phone number of the technician involved]- Call Responses: [Do not give any details about calls made or received]- On-Call Work Acknowledgment: [Do not mention if the work request was accepted and by whom] Ignore UET Problem Tickets:- UET Problem Ticket Numbers: [Do not list any ticket numbers]- Dates and Times: [Do not list the clear times and dates for each resolved ticket]- Action Taken: [Do not specify the action taken for each ticket, e.g., Auto Closed] Ignore any system alerts and acknowledgments:- System Alerts: [Do not describe any system-generated alerts, e.g., POI Alarms]- Auto Acknowledgment: [Do not indicate if alerts were acknowledged automatically by systems, such as ISA_Auto, Auto Resolved, Auto Closed] Ignore the details of affected services and devices:- Node Affected: [Do not indicate the node number and location]- Offline Statistics: [Do not provide statistics on the percentage offline and devices affected]- Customer Impact: [Do not list the impact on business and residential customers, if any] Ignore information on any work requests:- Priority Level: [Do not indicate the priority level of work requests]- Technicians Listed: [Do not list the names and contact numbers of technicians involved] Ignore any administrative or operational communications:- Email Exchanges: [Do not summarize the content of any email exchanges relevant to the incidents]- Ticket Dispatch Information: [Do not provide details of ticket creation and dispatch] Ignore any additional notes or incidents:- Additional Tickets: [Do not list any additional tickets resolved automatically]- Misc Issues: [Do not mention any other issues like incorrect ticket assignments or notes from the journal] Ensure the summary is in chronological order, maintaining clarity and conciseness.Here are some docs that might help you:<docs> [{\"node\":\"3WGB1\",\"journalid\":\"JNL000255945897\",\"incidentid\":\"UNO000037143793\",\"date_created\":\"2023-10-16 11:24:16.000\",\"journal_text\":\"UET Problem Ticket UNO000037143793 Auto Resolved\\n \\n Clear Time : 10\\/16\\/2023 7:24:16 AM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256335870\",\"incidentid\":\"UNO000037158773\",\"date_created\":\"2023-10-20 06:57:39.000\",\"journal_text\":\"Call to Tech BGRIMES (**********) for ticket UNO000037158773 was answered by unknown\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256335948\",\"incidentid\":\"UNO000037158773\",\"date_created\":\"2023-10-20 06:57:37.000\",\"journal_text\":\"On Call Work request for Node 3WGB1 was accepted by BGRIMES (**********)\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256337633\",\"incidentid\":\"UNO000037158773\",\"date_created\":\"2023-10-20 05:48:50.000\",\"journal_text\":\"Event Acknowledged By ISA_Auto\\n \\n (Active Outage Incident)\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256339153\",\"incidentid\":\"UNO000037158773\",\"date_created\":\"2023-10-20 07:15:31.000\",\"journal_text\":\"Commercial Power Outage.\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256339509\",\"incidentid\":\"UNO000037158773\",\"date_created\":\"2023-10-20 06:57:00.000\",\"journal_text\":\"Ticket: UNO000037158773. Candidates are : \\n TechId=BGRIMES, PhoneNumber=**********, Priority=1\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256339510\",\"incidentid\":\"UNO000037158773\",\"date_created\":\"2023-10-20 06:57:01.000\",\"journal_text\":\"Call initiated to tech BGRIMES (**********) for ticket UNO000037158773\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256341122\",\"incidentid\":\"UNO000037158773\",\"date_created\":\"2023-10-20 07:21:44.000\",\"journal_text\":\"see journals\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256341594\",\"incidentid\":\"UNO000037156826\",\"date_created\":\"2023-10-20 07:18:22.000\",\"journal_text\":\"UET Problem Ticket UNO000037156826 Auto Resolved\\n \\n Clear Time : 10\\/20\\/2023 3:18:18 AM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256412446\",\"incidentid\":\"UNO000037159469\",\"date_created\":\"2023-10-20 22:42:15.000\",\"journal_text\":\"UET Problem Ticket UNO000037159469 Auto Resolved\\n \\n Clear Time : 10\\/20\\/2023 6:42:15 PM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256468648\",\"incidentid\":\"UNO000037163487\",\"date_created\":\"2023-10-21 20:03:06.000\",\"journal_text\":\"UET Problem Ticket UNO000037163487 Auto Resolved\\n \\n Clear Time : 10\\/21\\/2023 4:03:06 PM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256639621\",\"incidentid\":\"UNO000037172457\",\"date_created\":\"2023-10-24 02:00:53.000\",\"journal_text\":\"Event Acknowledged By ISA_Auto\\n \\n (Active Outage Incident)\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256639876\",\"incidentid\":\"UNO000037169800\",\"date_created\":\"2023-10-24 02:03:18.000\",\"journal_text\":\"UET Problem Ticket UNO000037169800 Auto Resolved\\n \\n Clear Time : 10\\/23\\/2023 10:03:18 PM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256642401\",\"incidentid\":\"UNO000037172457\",\"date_created\":\"2023-10-24 03:35:56.000\",\"journal_text\":\"On Call Work request for Node 3WGB1 was accepted by BGRIMES (**********)\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256642402\",\"incidentid\":\"UNO000037172457\",\"date_created\":\"2023-10-24 03:35:58.000\",\"journal_text\":\"Call to Tech BGRIMES (**********) for ticket UNO000037172457 was answered by unknown\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256642697\",\"incidentid\":\"UNO000037172457\",\"date_created\":\"2023-10-24 03:35:19.000\",\"journal_text\":\"Ticket: UNO000037172457. Candidates are : \\n TechId=BGRIMES, PhoneNumber=**********, Priority=1\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256643477\",\"incidentid\":\"UNO000037172457\",\"date_created\":\"2023-10-24 03:35:20.000\",\"journal_text\":\"Call initiated to tech BGRIMES (**********) for ticket UNO000037172457\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256647421\",\"incidentid\":\"UNO000037171617\",\"date_created\":\"2023-10-24 05:42:20.000\",\"journal_text\":\"UET Problem Ticket UNO000037171617 Auto Resolved\\n \\n Clear Time : 10\\/24\\/2023 1:42:16 AM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256648355\",\"incidentid\":\"UNO000037172457\",\"date_created\":\"2023-10-24 06:06:43.000\",\"journal_text\":\"See Journals\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256649112\",\"incidentid\":\"UNO000037172457\",\"date_created\":\"2023-10-24 06:05:35.000\",\"journal_text\":\"Issue was initially due to ingress, by the time I got onsite the node was down. Rebooted the node and all services were restored. Still a slight noise issue but is not causing any equipment to be offline. The equipment currently offline is due to the node being rebooted.\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256719858\",\"incidentid\":\"UNO000037174022\",\"date_created\":\"2023-10-24 20:43:03.000\",\"journal_text\":\"UET Problem Ticket UNO000037174022 Auto Resolved\\n \\n Clear Time : 10\\/24\\/2023 4:43:03 PM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256837588\",\"incidentid\":\"UNO000037178197\",\"date_created\":\"2023-10-25 22:03:38.000\",\"journal_text\":\"UET Problem Ticket UNO000037178197 Auto Resolved\\n \\n Clear Time : 10\\/25\\/2023 6:03:38 PM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000256952131\",\"incidentid\":\"UNO000037182727\",\"date_created\":\"2023-10-27 01:24:15.000\",\"journal_text\":\"UET Problem Ticket UNO000037182727 Auto Resolved\\n \\n Clear Time : 10\\/26\\/2023 9:24:15 PM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000257057773\",\"incidentid\":\"UNO000037186377\",\"date_created\":\"2023-10-28 04:02:54.000\",\"journal_text\":\"UET Problem Ticket UNO000037186377 Auto Resolved\\n \\n Clear Time : 10\\/28\\/2023 12:02:54 AM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000257084080\",\"incidentid\":\"UNO000037191238\",\"date_created\":\"2023-10-28 14:36:55.000\",\"journal_text\":\"Event Acknowledged By ISA_Auto\\n \\n (Active Outage Incident)\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000257084538\",\"incidentid\":\"UNO000037190297\",\"date_created\":\"2023-10-28 15:23:06.000\",\"journal_text\":\"UET Problem Ticket UNO000037190297 Auto Resolved\\n \\n Clear Time : 10\\/28\\/2023 11:23:06 AM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000257185687\",\"incidentid\":\"UNO000037192584\",\"date_created\":\"2023-10-30 07:04:15.000\",\"journal_text\":\"UET Problem Ticket UNO000037192584 Auto Resolved\\n \\n Clear Time : 10\\/30\\/2023 3:04:10 AM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000257252721\",\"incidentid\":\"UNO000037193015\",\"date_created\":\"2023-10-30 21:26:38.000\",\"journal_text\":\"UET Problem Ticket UNO000037193015 Auto Resolved\\n \\n Clear Time : 10\\/30\\/2023 5:26:38 PM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000257373250\",\"incidentid\":\"UNO000037200930\",\"date_created\":\"2023-11-01 02:43:04.000\",\"journal_text\":\"UET Problem Ticket UNO000037200930 Auto Resolved\\n \\n Clear Time : 10\\/31\\/2023 10:43:04 PM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000257381148\",\"incidentid\":\"UNO000037202255\",\"date_created\":\"2023-11-01 06:09:17.000\",\"journal_text\":\"UET Problem Ticket UNO000037202255 Auto Resolved\\n \\n Clear Time : 11\\/1\\/2023 2:09:14 AM\\n Action Taken : Auto Closed\"},{\"node\":\"3WGB1\",\"journalid\":\"JNL000257394601\",\"incidentid\":\"UNO000037198161\",\"date_created\":\"2023-11-01 07:04:54.000\",\"journal_text\":\"UET Problem Ticket UNO000037198161 Auto Resolved\\n \\n Clear Time : 11\\/1\\/2023 3:04:35 AM\\n Action Taken : Auto Closed\"}] </docs>"""

test_prompt = """Hello! What is your name?"""
class ApiGatewayWebsocket:
    """Encapsulates Amazon API Gateway websocket functions."""

    def __init__(self, api_name, apig2_client):
        """
        :param api_name: The name of the websocket API.
        :param apig2_client: A Boto3 API Gateway V2 client.
        """
        self.apig2_client = apig2_client
        self.api_name = api_name
        self.api_id = None
        self.api_endpoint = None
        self.api_arn = None
        self.stage = None

    permission_policy_suffix = "manage-connections"

    def create_api(self, route_selection):
        """
        Creates a websocket API. The newly created API has no routes.

        :param route_selection: Used to determine route selection. For example,
                                specifying 'request.body.action' looks for an 'action'
                                field in the request body and uses the value of that
                                field to route requests.
        :return: The ID of the newly created API.
        """
        try:
            response = self.apig2_client.create_api(
                Name=self.api_name,
                ProtocolType="WEBSOCKET",
                RouteSelectionExpression=route_selection,
            )
            self.api_id = response["ApiId"]
            self.api_endpoint = response["ApiEndpoint"]
            logger.info(
                "Created websocket API %s with ID %s.", self.api_name, self.api_id
            )
        except ClientError:
            logger.exception("Couldn't create websocket API %s.", self.api_name)
            raise
        else:
            return self.api_id

    def add_connection_permissions(self, account, lambda_role_name, iam_resource):
        """
        Adds permission to let the AWS Lambda handler access connections through the
        API Gateway Management API. This is required so the Lambda handler can
        post messages to other chat participants.

        :param account: The AWS account number of the account that owns the
                        websocket API.
        :param lambda_role_name: The name of the role used by the AWS Lambda function.
                                 The connection permission policy is attached to this
                                 role.
        :param iam_resource: A Boto3 AWS Identity and Access Management (IAM) resource.
        """
        self.api_arn = (
            f"arn:aws:execute-api:{self.apig2_client.meta.region_name}:"
            f"{account}:{self.api_id}/*"
        )
        policy = None
        try:
            policy = iam_resource.create_policy(
                PolicyName=f"{lambda_role_name}-{self.permission_policy_suffix}",
                PolicyDocument=json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["execute-api:ManageConnections"],
                                "Resource": self.api_arn,
                            }
                        ],
                    }
                ),
            )
            policy.attach_role(RoleName=lambda_role_name)
            logger.info(
                "Created and attached policy %s to Lambda role.", policy.policy_name
            )
        except ClientError:
            if policy is not None:
                policy.delete()
            logger.exception(
                "Couldn't create or attach policy to Lambda role %s.", lambda_role_name
            )
            raise

    def remove_connection_permissions(self, lambda_role):
        """
        Removes the connection permission policy from the AWS Lambda function's role
        and deletes the policy.

        :param lambda_role: The role that is attached to the connection permission
                            policy.
        """
        policy_name = f"{lambda_role.name}-{self.permission_policy_suffix}"
        try:
            for policy in lambda_role.attached_policies.all():
                if policy.policy_name == policy_name:
                    lambda_role.detach_policy(PolicyArn=policy.arn)
                    policy.delete()
                    break
            logger.info("Detached and deleted connection policy %s.", policy_name)
        except ClientError:
            logger.exception(
                "Couldn't detach or delete connection policy %s.", policy_name
            )
            raise

    def add_route_and_integration(self, route_name, lambda_func, lambda_client):
        """
        Adds a route to the websocket API and an integration to a Lambda
        function that is used to handle the request.

        Also adds permission to let API Gateway invoke the Lambda function from
        the specified route.

        :param route_name: The name of the new route. This is used as the last part
                           of the route URI. The special routes $connect, $disconnect,
                           and $default can be specified as well as custom routes.
        :param lambda_func: The Lambda function that handles a request to the route.
        :param lambda_client: A Boto3 Lambda client.
        :return: The ID of the newly added route.
        """
        integration_uri = (
            f"arn:aws:apigateway:{self.apig2_client.meta.region_name}:lambda:"
            f'path/2015-03-31/functions/{lambda_func["FunctionArn"]}/invocations'
        )
        try:
            response = self.apig2_client.create_integration(
                ApiId=self.api_id,
                IntegrationType="AWS_PROXY",
                IntegrationMethod="POST",
                IntegrationUri=integration_uri,
            )
            logging.info("Created integration to %s.", integration_uri)
        except ClientError:
            logging.exception("Couldn't create integration to %s.", integration_uri)
            raise
        else:
            integration_id = response["IntegrationId"]

        target = f"integrations/{integration_id}"
        try:
            response = self.apig2_client.create_route(
                ApiId=self.api_id, RouteKey=route_name, Target=target
            )
            logger.info("Created route %s to %s.", route_name, target)
        except ClientError:
            logger.exception("Couldn't create route %s to %s.", route_name, target)
            raise
        else:
            route_id = response["RouteId"]

        source_arn = f"{self.api_arn}/{route_name}"
        try:
            alpha_route = route_name[1:] if route_name[0] == "$" else route_name
            lambda_client.add_permission(
                FunctionName=lambda_func["FunctionName"],
                StatementId=f"{self.api_name}-{alpha_route}-invoke",
                Action="lambda:InvokeFunction",
                Principal="apigateway.amazonaws.com",
                SourceArn=source_arn,
            )
            logger.info(
                "Added permission to let API Gateway invoke Lambda function %s "
                "from the new route.",
                lambda_func["FunctionName"],
            )
        except ClientError:
            logger.exception(
                "Couldn't add permission to AWS Lambda function %s.",
                lambda_func["FunctionName"],
            )
            raise

        return route_id

    def deploy_api(self, stage):
        """
        Deploys an API stage, which lets clients send requests to it.
        The stage must be appended to the endpoint URI when sending requests to
        the API.

        :param stage: The name of the stage.
        :return: The endpoint URI for the deployed stage.
        """
        try:
            self.apig2_client.create_stage(
                ApiId=self.api_id, AutoDeploy=True, StageName=stage
            )
            self.stage = stage
            logger.info("Created and deployed stage %s.", stage)
        except ClientError:
            logger.exception("Couldn't create deployment stage %s.", stage)
            raise

        return f"{self.api_endpoint}/{self.stage}"

    def get_websocket_api_info(self):
        """
        Gets data about a websocket API by name. This function scans API Gateway
        APIs in the current account and selects the first one that matches the
        API name.

        :return: The ID and endpoint URI of the named API.
        """
        self.api_id = None
        paginator = self.apig2_client.get_paginator("get_apis")
        for page in paginator.paginate():
            for item in page["Items"]:
                if item["Name"] == self.api_name:
                    self.api_id = item["ApiId"]
                    self.api_endpoint = item["ApiEndpoint"]
                    return self.api_id, self.api_endpoint
        raise ValueError

    def delete_api(self):
        """
        Deletes an API Gateway API, including all of its routes and integrations.
        """
        try:
            api_id, _ = self.get_websocket_api_info()
            self.apig2_client.delete_api(ApiId=api_id)
            logger.info("Deleted API %s.", api_id)
        except ClientError:
            logger.exception("Couldn't delete websocket API.")
            raise


def deploy(stack_name, cf_resource):
    """
    Deploys prerequisite resources used by the `usage_demo` script. The resources are
    defined in the associated `setup.yaml` AWS CloudFormation script and are deployed
    as a CloudFormation stack so they can be easily managed and destroyed.

    :param stack_name: The name of the CloudFormation stack.
    :param cf_resource: A Boto3 CloudFormation resource.
    """
    print(f"Creating and deploying stack {stack_name}.")
    with open("setup.yaml") as setup_file:
        setup_template = setup_file.read()
    stack = cf_resource.create_stack(
        StackName=stack_name,
        TemplateBody=setup_template,
        Capabilities=["CAPABILITY_NAMED_IAM"],
    )
    print("Waiting for stack to deploy. This typically takes about 1 minute.")
    waiter = cf_resource.meta.client.get_waiter("stack_create_complete")
    waiter.wait(StackName=stack.name)
    stack.load()
    print(f"Stack status: {stack.stack_status}")
    print("Created resources:")
    for resource in stack.resource_summaries.all():
        print(f"\t{resource.resource_type}, {resource.physical_resource_id}")


def usage_demo(
    sock_gateway,
    account,
    lambda_role_name,
    iam_resource,
    lambda_function_name,
    lambda_client,
):
    """
    Shows how to use the API Gateway API to create and deploy a websocket API that is
    backed by a Lambda function.

    :param sock_gateway: The API Gateway websocket wrapper object.
    :param account: The AWS account number of the current account.
    :param lambda_role_name: The name of an existing role that is associated with
                             the Lambda function. A policy is attached to this role
                             that lets the Lambda function call the API Gateway
                             Management API.
    :param iam_resource: A Boto3 IAM resource.
    :param lambda_function_name: The name of an existing Lambda function that can
                                 handle websocket requests.
    :param lambda_client: A Boto3 Lambda client.
    """
    lambda_file_name = "lambda_chat.py"
    print(
        f"Updating Lambda function {lambda_function_name} with example code file "
        f"{lambda_file_name}."
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.write(lambda_file_name)
    buffer.seek(0)
    try:
        lambda_func = lambda_client.update_function_code(
            FunctionName=lambda_function_name, ZipFile=buffer.read()
        )
    except ClientError:
        logger.exception("Couldn't update Lambda function %s.", lambda_function_name)
        raise

    print(f"Creating websocket chat API {sock_gateway.api_name}.")
    sock_gateway.create_api("$request.body.action")

    print(
        "Adding permission to let the Lambda function send messages to "
        "websocket connections."
    )
    sock_gateway.add_connection_permissions(account, lambda_role_name, iam_resource)

    print("Adding routes to the chat API and integrating with the Lambda function.")
    for route in ["$connect", "$disconnect", "sendmessage"]:
        sock_gateway.add_route_and_integration(route, lambda_func, lambda_client)

    print("Deploying the API to stage test.")
    chat_uri = sock_gateway.deploy_api("test")

    print(
        "Try it yourself! Connect a websocket client to the chat URI to start a "
        "chat."
    )
    print(f"\tChat URI: {chat_uri}")
    print("Send messages in this format:")
    print('\t{"action": "sendmessage", "prompt": "YOUR MESSAGE HERE"}')


async def chat_demo(uri):
    """
    Shows how to use the deployed websocket API to connect users to the chat
    application and send messages to them.

    The demo connects three passive users who listen for messages, and one active
    user who sends messages to the other users through the websocket API.

    :param uri: The websocket URI of the chat application.
    """
    uri = "wss://8b9ldf1092.execute-api.us-east-1.amazonaws.com/prod"

    async def receiver(name):
        async with websockets.connect(f"{uri}?name={name}") as socket:
            print(f"> Connected to {uri}. Hello, {name}!")
            msg = ""
            while "Bye" not in msg:
                msg = await socket.recv()
                print(f"> {name} got message: {msg}")

    async def sender(name):
        async with websockets.connect(f"{uri}?name={name}") as socket:
            for msg in ("Hello everyone!", "Not much to say...", test_prompt, "Bye!"):
                await asyncio.sleep(1)
                print(f"< {name}: {msg}")
                await socket.send(json.dumps({"action": "sendmessage", "prompt": msg}))

    await asyncio.gather(
        *(receiver(user) for user in ("Ryan",)), sender("CoxAssistant")
    )


def destroy(sock_gateway, lambda_role_name, iam_resource, stack, cf_resource):
    """
    Removes the connection permission policy added to the Lambda role, deletes the
    API Gateway websocket API, destroys the resources managed by the CloudFormation
    stack, and deletes the CloudFormation stack itself.

    :param sock_gateway: The API Gateway websocket wrapper object.
    :param lambda_role_name: The name of the Lambda role that has the connection
                             permission policy attached.
    :param iam_resource: A Boto3 IAM resource.
    :param stack: The CloudFormation stack that manages the demo resources.
    :param cf_resource: A Boto3 CloudFormation resource.
    """
    print(f"Deleting websocket API {sock_gateway.api_name}.")
    sock_gateway.remove_connection_permissions(iam_resource.Role(lambda_role_name))
    sock_gateway.delete_api()

    print(f"Deleting stack {stack.name}.")
    stack.delete()
    print("Waiting for stack removal.")
    waiter = cf_resource.meta.client.get_waiter("stack_delete_complete")
    waiter.wait(StackName=stack.name)
    print("Stack delete complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Runs the Amazon API Gateway websocket chat demo. Run this script "
        "with the 'deploy' flag to deploy prerequisite resources, with the "
        "'demo' flag to see how to create and deploy a websocket chat API, "
        "and with the 'chat' flag to see an automated demo of using the "
        "chat API from a websocket client. Run with the 'destroy' flag to "
        "clean up all resources."
    )
    parser.add_argument(
        "action",
        choices=["deploy", "demo", "chat", "destroy"],
        help="Indicates the action the script performs.",
    )
    args = parser.parse_args()

    print("-" * 88)
    print("Welcome to the Amazon API Gateway websocket chat demo!")
    print("-" * 88)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    cf_resource = boto3.resource("cloudformation")
    stack = cf_resource.Stack("python-example-code-apigateway-websocket-chat")
    sock_gateway = ApiGatewayWebsocket(stack.name, boto3.client("apigatewayv2"))

    if args.action == "deploy":
        print("Deploying prerequisite resources for the demo.")
        deploy(stack.name, cf_resource)
        print("To see example usage, run the script again with the 'demo' flag.")
    elif args.action == "chat":
        print("Starting websocket chat demo.")
        # _, api_endpoint = sock_gateway.get_websocket_api_info()
        asyncio.run(chat_demo(f"x"))
        print(
            "To remove resources created for the demo, run the script again with "
            "the 'destroy' flag."
        )
    elif args.action in ["demo", "destroy"]:
        lambda_role_name = None
        lambda_function_name = None
        for resource in stack.resource_summaries.all():
            if resource.resource_type == "AWS::IAM::Role":
                lambda_role_name = resource.physical_resource_id
            elif resource.resource_type == "AWS::Lambda::Function":
                lambda_function_name = resource.physical_resource_id
        if args.action == "demo":
            print(
                "Demonstrating how to use Amazon API Gateway to create a websocket "
                "chat application."
            )
            account = boto3.client("sts").get_caller_identity().get("Account")
            usage_demo(
                sock_gateway,
                account,
                lambda_role_name,
                boto3.resource("iam"),
                lambda_function_name,
                boto3.client("lambda"),
            )
            print(
                "To see an automated demo of how to use the chat API from a "
                "websocket client, run the script again with the 'chat' flag."
            )
            print(
                "When you're done, clean up all AWS resources created for the demo "
                "by running the script with the 'destroy' flag."
            )
        elif args.action == "destroy":
            print("Destroying AWS resources created for the demo.")
            destroy(
                sock_gateway,
                lambda_role_name,
                boto3.resource("iam"),
                stack,
                cf_resource,
            )
            print("Thanks for watching!")

    print("-" * 88)


if __name__ == "__main__":
    main()
