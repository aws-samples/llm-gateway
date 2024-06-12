import { APIGatewayRequestAuthorizerHandler } from "aws-lambda";
import { CognitoJwtVerifier } from "aws-jwt-verify";
import fetch from 'node-fetch';
// import { DynamoDBClient, QueryCommand } from "@aws-sdk/client-dynamodb";
// import { SecretsManager } from "@aws-sdk/client-secrets-manager";
// import { createHash } from 'crypto';

const UserPoolId = process.env.USER_POOL_ID!;
const AppClientId = process.env.APP_CLIENT_ID!;
const AdminOnly = process.env.ADMIN_ONLY?.toLowerCase() === 'true';

const AdminList = process.env.ADMIN_LIST ? process.env.ADMIN_LIST.split(',').map(item => item.trim()) : [];
const CognitoDomainPrefix = process.env.COGNITO_DOMAIN_PREFIX!
const Region = process.env.REGION!

console.log("AdminOnly:", AdminOnly);
console.log("AdminList:", AdminList);
console.log("CognitoDomainPrefix:", CognitoDomainPrefix);
console.log("Region:", Region);

async function getUsername(encodedToken: string): Promise<string> {
  const userInfo = await getUserInfo(encodedToken);
  return userInfo.username;
}

async function getUserInfo(encodedToken: string): Promise<any> {

  const url = `https://${CognitoDomainPrefix}.auth.${Region}.amazoncognito.com/oauth2/userInfo`;

  const headers = {
      'Authorization': `Bearer ${encodedToken}`
  };

  try {
      const response = await fetch(url, { headers });
      if (response.ok) {
          return await response.json(); // Returns the user info as a JSON object
      } else {
          return { statusCode: response.status, statusText: await response.text() }; // Returns error status and message if not successful
      }
  } catch (error) {
      console.error('Request failed:', error);
      throw error; // Throw an error to handle it in the caller function
  }
}


export const handler: APIGatewayRequestAuthorizerHandler = async (event, context) => {
  try {
    const verifier = CognitoJwtVerifier.create({
      userPoolId: UserPoolId,
      tokenUse: "access",
      clientId: AppClientId,
    });
    console.log("Event:", event);

    const encodedToken = getEncodedToken(event);

    const payload = await verifier.verify(encodedToken);
    console.log("Token is valid. Payload:", payload);

    if (AdminOnly){
        const username = await getUsername(encodedToken);

        if (!AdminList.includes(username)) {
            console.log(`User ${username} is not an admin, denying access.`)
            return denyAllPolicy();
        }
        console.log(`User ${username} is an admin, granting access.`)

    } else {
      console.log("User doesn't need to be an admin, granting access.")
    }

    return allowPolicy(event.methodArn, payload);
  } catch (error: any) {
    console.log(error.message);
    return denyAllPolicy();
  }
};

function getEncodedToken(event: any) {
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
  return tokenParts[1];
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