import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { LlmGatewayStack } from "../lib/llmGateway";
import { AwsSolutionsChecks, NagSuppressions } from "cdk-nag";
import { Aspects } from "aws-cdk-lib";

const app = new cdk.App();

// Use cdk-nag to check for potential security issues
Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));

const stack = new LlmGatewayStack(app, "LlmGatewayStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});

// Suppress some cdk-nag rules.
NagSuppressions.addStackSuppressions(stack, [
  {
    id: "AwsSolutions-COG4",
    reason: "OPTION endpoints shouldn't have authorization.",
  },
  {
    id: "AwsSolutions-APIG6",
    reason: "This isn't essential.",
  },
  // Uncomment the lines below this one, to re-run these checks.
  {
    id: "AwsSolutions-IAM5",
    reason:
      "I have checked all these permissions -- they are correct and minimal.",
  },
  {
    id: "AwsSolutions-APIG4",
    reason: "Websockets don't have this as an option yet.",
  },
  {
    id: "AwsSolutions-APIG1",
    reason: "Websockets don't have this option yet.",
  },
]);
