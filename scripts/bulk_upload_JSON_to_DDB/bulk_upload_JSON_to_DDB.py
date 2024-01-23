import boto3
import argparse
import json

# Initialize a DynamoDB client
dynamodb = boto3.resource('dynamodb')


def upload_json_to_dynamodb(file_path, table_name):
    """Uploads each JSON object to DDB using the AWS SDK."""
    # Get a reference to the DynamoDB table
    table = dynamodb.Table(table_name)

    with open(file_path, 'r') as file:
        data = json.load(file)
        for item in data:
            # Perform the bulk insert
            table.put_item(Item=item)


def main():
    parser = argparse.ArgumentParser(description='Upload many JSON objects into DynamoDB, in bulk.')
    parser.add_argument('json_file', type=str, help='Path to the JSON file containing objects to upload')
    parser.add_argument("-t", "--table-name", type=str, required=True, help='Path to the JSON file containing objects to upload')
    args = parser.parse_args()

    file_path = args.json_file
    table_name = args.table_name
    upload_json_to_dynamodb(file_path, table_name)


if __name__ == "__main__":
    main()
