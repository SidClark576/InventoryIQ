import json
import os
import boto3
from boto3.dynamodb.conditions import Attr

# Initialize DynamoDB with inventory table
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

# Standard CORS headers for POST requests
CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
}

def lambda_handler(event, _context):
    """
    Deletes a category by reassigning all items in that category to "Uncategorized".

    Flow:
    1. Handle CORS preflight OPTIONS request
    2. Parse request body and extract userID and categoryName
    3. Prevent deletion of "Uncategorized" category (system requirement)
    4. Scan for all items with matching category and userID
    5. Update each item: set category to "Uncategorized"
    6. Return count of items updated

    Request Body:
    - userID: Required. User email who owns the items
    - categoryName: Required. Category name to delete

    Response: {'itemsUpdated': N} where N is number of items reassigned

    Design Note: "Uncategorized" is not actually deleted, items are reassigned to it.
    This prevents orphaned items and ensures no data loss.
    """
    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    # Extract userID from query parameters and categoryName from URL path
    # DELETE /categories/{categoryName}?userID=<email>
    params = event.get('queryStringParameters') or {}
    user_id = params.get('userID', '')
    category_name = (event.get('pathParameters') or {}).get('categoryName', '')

    # Validate required fields
    if not user_id or not category_name:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'userID and categoryName required'})}

    # Prevent deletion of the "Uncategorized" category
    # This is a system category that must always exist as a fallback
    if category_name.lower() == 'uncategorized':
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'Cannot delete Uncategorized'})}

    # Scan for all items with this specific category and userID
    # Use compound filter: must match BOTH userID (for multi-tenancy) AND category
    result = table.scan(
        FilterExpression=Attr('userID').eq(user_id) & Attr('category').eq(category_name)
    )
    items = result.get('Items', [])

    # Pagination loop: handle DynamoDB scan limit (1MB per request)
    while 'LastEvaluatedKey' in result:
        result = table.scan(
            ExclusiveStartKey=result['LastEvaluatedKey'],
            FilterExpression=Attr('userID').eq(user_id) & Attr('category').eq(category_name)
        )
        items.extend(result.get('Items', []))

    # Update each item: reassign category to "Uncategorized"
    # This prevents orphaned items and ensures smooth category deletion
    items_updated = 0
    for item in items:
        table.update_item(
            Key={'itemID': item['itemID']},
            UpdateExpression='SET category = :cat',
            ExpressionAttributeValues={':cat': 'Uncategorized'}
        )
        items_updated += 1

    # Return the count of items updated
    # This informs the frontend how many items were reassigned
    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps({'itemsUpdated': items_updated})}
