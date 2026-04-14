import json
import os
import boto3
from boto3.dynamodb.conditions import Attr

# Initialize DynamoDB with inventory table
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

# Standard CORS headers for GET requests
CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,GET'
}

def lambda_handler(event, context):
    """
    Retrieves all unique categories for a user's inventory items.

    Flow:
    1. Handle CORS preflight OPTIONS request
    2. Extract and validate userID from query parameters
    3. Scan inventory items filtering by userID
    4. Extract unique category values from all items
    5. Sort alphabetically
    6. Ensure "Uncategorized" is always included (even if no items have it)
    7. Return sorted list of category strings

    Query Parameters:
    - userID: Required. Email of user to get categories for.

    Response: Array of category strings, always includes "Uncategorized"

    Note: "Uncategorized" is always returned because:
    1. It's the default category for new items
    2. Users can move items to it when deleting a category
    3. Ensures UI always has at least one category option
    """
    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    # Extract and validate userID
    user_id = (event.get('queryStringParameters') or {}).get('userID', '')
    if not user_id:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'userID required'})}

    # Scan all items for this user
    result = table.scan(FilterExpression=Attr('userID').eq(user_id))
    items = result.get('Items', [])

    # Pagination loop: handle DynamoDB scan limit (1MB per request)
    while 'LastEvaluatedKey' in result:
        result = table.scan(
            ExclusiveStartKey=result['LastEvaluatedKey'],
            FilterExpression=Attr('userID').eq(user_id)
        )
        items.extend(result.get('Items', []))

    # Extract unique categories from all items
    # Set() removes duplicates, sorted() orders alphabetically
    categories = sorted(list(set(
        item.get('category', 'Uncategorized')
        for item in items
        if item.get('category')  # Filter out None/empty values
    )))

    # Always include "Uncategorized" even if user has no items with that category
    # This ensures the dropdown always has at least one option
    # and prevents errors when no items exist for that category explicitly
    if 'Uncategorized' not in categories:
        categories.append('Uncategorized')
        categories.sort()

    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(categories)}
