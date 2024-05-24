import fetch from "node-fetch";
import parser from "lambda-multipart-parser";

import { APIGatewayProxyHandlerV2 } from "aws-lambda";

export const handler: APIGatewayProxyHandlerV2 = async (event) => {
  const result = await parser.parse(event);
  console.log("Client ID:", result.client_id);
  console.log("Client Secret:", result.client_secret); // Caution: Very sensitive!
  console.log("Code:", result.code);
  try {
    // Fetch the token from GitHub OAuth
    const tokenResponse = await fetch(
      `https://github.com/login/oauth/access_token?client_id=${result.client_id}&client_secret=${result.client_secret}&code=${result.code}`,
      {
        method: "POST",
        headers: {
          accept: "application/json",
        },
      }
    );

    // Log the HTTP response status
    console.log("HTTP Status Code:", tokenResponse.status);
    
    // Check if the response was successful
    if (!tokenResponse.ok) {
      const error = await tokenResponse.text(); // Or use .json() if the error response is in JSON format
      console.log("HTTP Error Response:", error);
    }

    const token = await tokenResponse.json();
    
    // Log the full token response
    console.log("OAuth Token Response:", token);

    return token;
  } catch (error) {
    console.error("Error fetching token:", error);
    return { statusCode: 500, body: 'Internal Server Error' };
  }
};