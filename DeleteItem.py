import json
import uuid
import boto3
import os
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
tx_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

def lambda_handler(event, context):
    try:
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        # Read existing item before deletion for transaction record
        existing = table.get_item(Key={'itemID': item_id}).get('Item', {})

        table.delete_item(Key={'itemID': item_id})

        # Write transaction record
        tx_table.put_item(Item={
            'transactionID': str(uuid.uuid4()),
            'itemID': item_id,
            'itemName': existing.get('name', ''),
            'userID': existing.get('userID', ''),
            'changeType': 'delete',
            'quantityBefore': int(existing.get('quantity', 0)),
            'quantityAfter': 0,
            'quantityDelta': -int(existing.get('quantity', 0)),
            'notes': 'Item deleted',
            'createdAt': datetime.utcnow().isoformat()
        })

        return response(200, {'message': f'Item {item_id} deleted successfully'})

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
