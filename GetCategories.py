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
    'Access-Control-Allow-Methods': 'OPTIONS,GET'
}

def lambda_handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    user_id = (event.get('queryStringParameters') or {}).get('userID', '')
    if not user_id:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'userID required'})}

    result = table.scan(FilterExpression=Attr('userID').eq(user_id))
    items = result.get('Items', [])
    while 'LastEvaluatedKey' in result:
        result = table.scan(
            ExclusiveStartKey=result['LastEvaluatedKey'],
            FilterExpression=Attr('userID').eq(user_id)
        )
        items.extend(result.get('Items', []))

    categories = sorted(list(set(
        item.get('category', 'Uncategorized')
        for item in items
        if item.get('category')
    )))

    # Always include "Uncategorized" even if no items have it explicitly
    if 'Uncategorized' not in categories:
        categories.append('Uncategorized')
        categories.sort()

    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(categories)}
