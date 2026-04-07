import json
import os
import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,POST'
}

def lambda_handler(event, _context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    try:
        body = json.loads(event.get('body', '{}'))
    except:
        body = {}

    user_id = body.get('userID', '')
    category_name = body.get('categoryName', '')

    if not user_id or not category_name:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'userID and categoryName required'})}

    # Prevent deletion of "Uncategorized"
    if category_name.lower() == 'uncategorized':
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'Cannot delete Uncategorized'})}

    # Scan for all items with this category and userID
    result = table.scan(
        FilterExpression=Attr('userID').eq(user_id) & Attr('category').eq(category_name)
    )
    items = result.get('Items', [])
    while 'LastEvaluatedKey' in result:
        result = table.scan(
            ExclusiveStartKey=result['LastEvaluatedKey'],
            FilterExpression=Attr('userID').eq(user_id) & Attr('category').eq(category_name)
        )
        items.extend(result.get('Items', []))

    # Update each item's category to "Uncategorized"
    items_updated = 0
    for item in items:
        table.update_item(
            Key={'itemID': item['itemID']},
            UpdateExpression='SET category = :cat',
            ExpressionAttributeValues={':cat': 'Uncategorized'}
        )
        items_updated += 1

    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps({'itemsUpdated': items_updated})}
