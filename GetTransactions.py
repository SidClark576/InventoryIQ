import json
import os
import boto3
from boto3.dynamodb.conditions import Attr
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

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

    # Convert Decimals to float
    for item in items:
        for k, v in item.items():
            if isinstance(v, Decimal):
                item[k] = float(v)

    # Sort newest first, limit 200
    items.sort(key=lambda x: x.get('createdAt', ''), reverse=True)

    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(items[:200])}
