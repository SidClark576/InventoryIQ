import json
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB resource and get the inventory table
# Table name is configurable via DYNAMODB_TABLE env var, defaults to 'InventoryIQ'
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

def lambda_handler(event, context):
    """
    Retrieves all inventory items for a specific user.

    Flow:
    1. Extract verified userID from X-Verified-UserID header (injected by Proxy.py)
    2. Return 401 if userID is missing (authentication requirement)
    3. Query GSI (userID-index) for all items belonging to user, handling pagination
    4. Convert Decimal types to float for JSON serialization
    5. Return items array with count

    Auth: X-Verified-UserID header (verified by Proxy.py after JWT validation)

    Response: {'items': [...], 'count': N}

    Performance: O(user items) using GSI, not O(total items) using scan.
    """
    try:
        # Extract verified userID from header (injected by Proxy.py after JWT validation)
        user_id = event.get('headers', {}).get('x-verified-userid', '').strip()
        if not user_id:
            return response(401, {'error': 'Missing or invalid authorization'})


        # Query GSI (userID-index) instead of full table scan
        # GSI structure: partition key = userID, sort key = createdAt
        # This scans only items belonging to this user, not entire table
        result = table.query(
            IndexName='userID-index',
            KeyConditionExpression=Key('userID').eq(user_id)
        )
        items = result.get('Items', [])

        # Handle pagination: DynamoDB query can return max 1MB at a time
        # LastEvaluatedKey indicates there are more results to fetch
        while 'LastEvaluatedKey' in result:
            result = table.query(
                IndexName='userID-index',
                KeyConditionExpression=Key('userID').eq(user_id),
                ExclusiveStartKey=result['LastEvaluatedKey']
            )
            items.extend(result.get('Items', []))

        # Convert Decimal types to float for JSON serialization
        # DynamoDB returns Decimal objects which cannot be JSON serialized by default
        items = [
            {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()}
            for item in items
        ]

        return response(200, {'items': items, 'count': len(items)})

    except Exception as e:
        return response(500, {'error': str(e)})

def response(status_code, body):
    """
    Helper function to format Lambda response with consistent headers and CORS.

    Args:
        status_code: HTTP status code
        body: Dictionary to be JSON-encoded

    Returns: API Gateway Lambda Proxy Integration response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key,Authorization',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
        },
        'body': json.dumps(body)
    }
