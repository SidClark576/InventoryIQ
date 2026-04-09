import json
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Attr

# Initialize DynamoDB resource and get the inventory table
# Table name is configurable via DYNAMODB_TABLE env var, defaults to 'InventoryIQ'
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

def lambda_handler(event, context):
    """
    Retrieves all inventory items for a specific user.

    Flow:
    1. Extract userID from query parameters
    2. Return empty list if userID is missing (user isolation requirement)
    3. Scan DynamoDB table filtering by userID, handling pagination
    4. Convert Decimal types to float for JSON serialization
    5. Return items array with count

    Query Parameters:
    - userID: Required. Email of the user to filter items by.

    Response: {'items': [...], 'count': N}
    """
    try:
        # Extract and validate userID from query parameters
        params = event.get('queryStringParameters') or {}
        user_id = params.get('userID', '').strip()

        # Return empty result if userID is not provided (prevents returning all items)
        if not user_id:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
                    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
                },
                'body': json.dumps({'items': [], 'count': 0})
            }

        # Initial scan with filter for userID
        result = table.scan(FilterExpression=Attr('userID').eq(user_id))
        items = result.get('Items', [])

        # Handle pagination: DynamoDB scan can return max 1MB at a time
        # LastEvaluatedKey indicates there are more results to fetch
        while 'LastEvaluatedKey' in result:
            result = table.scan(
                ExclusiveStartKey=result['LastEvaluatedKey'],
                FilterExpression=Attr('userID').eq(user_id)
            )
            items.extend(result.get('Items', []))

        # Convert Decimal types to float for JSON serialization
        # DynamoDB returns Decimal objects which cannot be JSON serialized by default
        items = [
            {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()}
            for item in items
        ]

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
                'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
            },
            'body': json.dumps({'items': items, 'count': len(items)})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
