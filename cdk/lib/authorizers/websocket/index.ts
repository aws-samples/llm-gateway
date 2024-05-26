import { APIGatewayRequestAuthorizerEvent, APIGatewayRequestAuthorizerHandler } from "aws-lambda";
import { CognitoJwtVerifier } from "aws-jwt-verify";
import { DynamoDBClient, QueryCommand } from "@aws-sdk/client-dynamodb";
import { createHash } from 'crypto';

const UserPoolId = process.env.USER_POOL_ID!;
const AppClientId = process.env.APP_CLIENT_ID!;
const awsRegion = process.env.AWS_REGION;
const apiKeyTableName = process.env.API_KEY_TABLE_NAME

interface ApiKeyDetails {
  username?: string;
  api_key_name?: string;
  api_key_id?: string;
}

export const handler: APIGatewayRequestAuthorizerHandler = async (event, context) => {
  try {
    const verifier = CognitoJwtVerifier.create({
      userPoolId: UserPoolId,
      tokenUse: "access",
      clientId: AppClientId,
    });
    console.log("Event:", event);

    // Ensure headers exist and get the token from the Authorization header
    const encodedToken = getEncodedTokenOrApiKey(event);

    const payload = await verifier.verify(encodedToken);
    console.log("Token is valid. Payload:", payload);

    return allowPolicy(event.methodArn, payload);
  } catch (error: any) {
    console.log(error.message);
    console.log("Event:", event);
    const apiKeyValue = getEncodedTokenOrApiKey(event);
    const apiKeyHash = hashApiKey(apiKeyValue)
    const itemDetails = await queryByApiKeyHash(apiKeyHash)
    try {
      if (itemDetails) {
        console.log("Username:", itemDetails.username);
        console.log("API Key Name:", itemDetails.api_key_name);
        console.log("API Key ID:", itemDetails.api_key_id);
        return allowPolicy(event.methodArn, itemDetails.username);
      } else {
        console.log("No items found for the provided API key hash.");
        return denyAllPolicy();
      }
    } catch (error: any) {
      console.log(error.message);
      return denyAllPolicy();
    }
  }
};

function hashApiKey(apiKeyValue: string): string {
  const hasher = createHash('sha256');
  hasher.update(apiKeyValue, 'utf-8'); // Ensure the input is treated as UTF-8 encoded string
  return hasher.digest('hex'); // Return the hash as a hexadecimal string
}


function getEncodedTokenOrApiKey(event: any) {
  // Ensure headers exist and get the token from the Authorization header
  const headers = event.headers;
  let authorizationHeader = undefined
  if (!headers){
    authorizationHeader = event.authorizationToken
  } else {
    authorizationHeader = headers.Authorization || headers.authorization;
  }

  if (!authorizationHeader) throw new Error("Authorization header is missing");

  const tokenParts = authorizationHeader.split(' ');
  if (tokenParts[0] !== 'Bearer' || tokenParts.length !== 2) throw new Error("Invalid Authorization token format");
  const encodedToken = tokenParts[1];
  return encodedToken;
}

async function queryByApiKeyHash(apiKeyHash: string): Promise<ApiKeyDetails | null> {
  const client = new DynamoDBClient({ region: awsRegion }); // Specify the AWS region
  const tableName = apiKeyTableName;

  const queryCommand = new QueryCommand({
      TableName: tableName,
      IndexName: "ApiKeyValueHashIndex",
      KeyConditionExpression: "api_key_value_hash = :hash_value",
      ExpressionAttributeValues: {
          ":hash_value": { S: apiKeyHash }
      },
  });

  try {
      const response = await client.send(queryCommand);
      const items = response.Items;

      if (items && items.length > 0) {
          const item = items[0];
          return {
              username: item.username?.S,
              api_key_name: item.api_key_name?.S,
              api_key_id: item.api_key_id?.S,
          };
      }
      return null;
  } catch (error) {
      console.error("Query failed:", error);
      return null;
  }
}

const denyAllPolicy = () => {
  return {
    principalId: "*",
    policyDocument: {
      Version: "2012-10-17",
      Statement: [
        {
          Action: "*",
          Effect: "Deny",
          Resource: "*",
        },
      ],
    },
  };
};

const allowPolicy = (methodArn: string, idToken: any) => {
  return {
    principalId: idToken.sub,
    policyDocument: {
      Version: "2012-10-17",
      Statement: [
        {
          Action: "execute-api:Invoke",
          Effect: "Allow",
          Resource: methodArn,
        },
      ],
    },
    context: {
      // set userId in the context
      userId: idToken.sub,
    },
  };
};