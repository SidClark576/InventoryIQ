import json
import boto3
import os
import uuid
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))

        if not body.get('name'):
            return response(400, {'error': 'Product name is required'})

        item_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        item = {
            'itemID': item_id,
            'name': body.get('name'),
            'description': body.get('description', ''),
            'category': body.get('category', 'Uncategorized'),
            'quantity': int(body.get('quantity', 0)),
            'price': Decimal(str(body.get('price', 0))),
            'lowStockThreshold': int(body.get('lowStockThreshold', 10)),
            'createdAt': timestamp,
            'updatedAt': timestamp
        }

        table.put_item(Item=item)
        item['price'] = float(item['price'])
        return response(201, {'message': 'Item added successfully', 'item': item})

    except Exception as e:
        return response(500, {'error': str(e)})

def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
        },
        'body': json.dumps(body)
    }