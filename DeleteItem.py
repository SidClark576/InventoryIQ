import json
import boto3
import os

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

def lambda_handler(event, context):
    try:
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        table.delete_item(Key={'itemID': item_id})
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