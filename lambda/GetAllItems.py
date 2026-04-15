import json
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr

# Initialize DynamoDB resource and get the inventory table
# Table name is configurable via DYNAMODB_TABLE env var, defaults to 'InventoryIQ'
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

def lambda_handler(event, context):
    """
    Retrieves all active (non-deleted) inventory items for a specific user.

    Sprint 3 change:
    - FilterExpression=Attr('deletedAt').not_exists() excludes soft-deleted items
      from both the initial query page and all paginated continuation pages

    Flow:
    1. Extract userID from query parameters
    2. Return empty list if userID is missing (user isolation requirement)
    3. Query userID-index GSI filtering by userID + excluding soft-deleted items
    4. Handle pagination (DynamoDB returns max 1MB per page)
    5. Convert Decimal types to float for JSON serialization
    6. Return items array with count

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

        # Query userID-index GSI for this user's items, excluding soft-deleted ones
        # FilterExpression is applied after the key condition; it does NOT reduce RCUs
        # but it does ensure soft-deleted items are never returned to the client
        result = table.query(
            IndexName='userID-index',
            KeyConditionExpression=Key('userID').eq(user_id),
            FilterExpression=Attr('deletedAt').not_exists()
        )
        items = result.get('Items', [])

        # Handle pagination: DynamoDB query returns max 1MB at a time
        # LastEvaluatedKey indicates there are more results to fetch
        while 'LastEvaluatedKey' in result:
            result = table.query(
                IndexName='userID-index',
                KeyConditionExpression=Key('userID').eq(user_id),
                FilterExpression=Attr('deletedAt').not_exists(),
                ExclusiveStartKey=result['LastEvaluatedKey']
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
