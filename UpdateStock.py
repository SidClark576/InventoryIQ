import json
import boto3
import os
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')

def lambda_handler(event, context):
    try:
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        body = json.loads(event.get('body', '{}'))
        timestamp = datetime.utcnow().isoformat()

        update_expr = "SET updatedAt = :ts"
        expr_values = {':ts': timestamp}
        expr_names = {}

        if 'quantity' in body:
            update_expr += ", quantity = :qty"
            expr_values[':qty'] = int(body['quantity'])
        if 'name' in body:
            update_expr += ", #nm = :name"
            expr_values[':name'] = body['name']
            expr_names['#nm'] = 'name'
        if 'price' in body:
            update_expr += ", price = :price"
            expr_values[':price'] = Decimal(str(body['price']))
        if 'category' in body:
            update_expr += ", category = :cat"
            expr_values[':cat'] = body['category']
        if 'description' in body:
            update_expr += ", description = :desc"
            expr_values[':desc'] = body['description']
        if 'lowStockThreshold' in body:
            update_expr += ", lowStockThreshold = :lst"
            expr_values[':lst'] = int(body['lowStockThreshold'])

        update_kwargs = {
            'Key': {'itemID': item_id},
            'UpdateExpression': update_expr,
            'ExpressionAttributeValues': expr_values,
            'ReturnValues': 'ALL_NEW'
        }
        if expr_names:
            update_kwargs['ExpressionAttributeNames'] = expr_names

        result = table.update_item(**update_kwargs)

        updated = result.get('Attributes', {})
        updated = {k: float(v) if isinstance(v, Decimal) else v for k, v in updated.items()}

        new_qty = int(updated.get('quantity', 9999))
        threshold = int(updated.get('lowStockThreshold', 10))
        item_name = updated.get('name', item_id)

        if SNS_TOPIC_ARN:
            if new_qty == 0:
                sns.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Subject='InventoryIQ — Item Out of Stock',
                    Message=f"🚨 {item_name} is now OUT OF STOCK. Reorder immediately."
                )
            elif new_qty <= threshold:
                sns.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Subject='InventoryIQ — Low Stock Warning',
                    Message=(
                        f"⚠️ {item_name} is running low.\n"
                        f"Current quantity: {new_qty} units\n"
                        f"Low-stock threshold: {threshold} units\n"
                        f"Please reorder soon."
                    )
                )

        return response(200, {'message': 'Item updated', 'item': updated})

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
