import json
import boto3
import os
from decimal import Decimal
from collections import defaultdict

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
sqs = boto3.client('sqs')

table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL', '')

def lambda_handler(event, context):
    try:
        result = table.scan()
        items = result.get('Items', [])
        while 'LastEvaluatedKey' in result:
            result = table.scan(ExclusiveStartKey=result['LastEvaluatedKey'])
            items.extend(result.get('Items', []))

        low_stock = []
        out_of_stock = []
        category_totals = defaultdict(int)
        total_value = Decimal('0')

        for item in items:
            qty = int(item.get('quantity', 0))
            threshold = int(item.get('lowStockThreshold', 10))
            price = Decimal(str(item.get('price', 0)))
            category = item.get('category', 'Uncategorized')

            category_totals[category] += qty
            total_value += Decimal(str(qty)) * price

            if qty == 0:
                out_of_stock.append({
                    'itemID': item['itemID'],
                    'name': item.get('name'),
                    'category': category,
                    'alert': '🚨 OUT OF STOCK — reorder immediately'
                })
            elif qty <= threshold:
                low_stock.append({
                    'itemID': item['itemID'],
                    'name': item.get('name'),
                    'quantity': qty,
                    'threshold': threshold,
                    'category': category,
                    'alert': f'⚠️ Low stock: only {qty} units left (threshold: {threshold})'
                })

        recommendations = []
        if out_of_stock:
            recommendations.append(f"🔴 {len(out_of_stock)} item(s) are completely out of stock. Place orders immediately.")
        if low_stock:
            recommendations.append(f"🟡 {len(low_stock)} item(s) are running low. Consider restocking soon.")
        if not items:
            recommendations.append("📦 No inventory found. Start by adding products.")
        if not out_of_stock and not low_stock and items:
            recommendations.append("✅ All stock levels are healthy!")

        insights = {
            'summary': {
                'totalProducts': len(items),
                'outOfStockCount': len(out_of_stock),
                'lowStockCount': len(low_stock),
                'estimatedInventoryValue': float(total_value)
            },
            'outOfStockItems': out_of_stock,
            'lowStockItems': low_stock,
            'categoryBreakdown': dict(category_totals),
            'recommendations': recommendations
        }

        alert_items = out_of_stock + low_stock
        if alert_items and SNS_TOPIC_ARN:
            lines = [f"InventoryIQ Stock Alert — {len(alert_items)} item(s) need attention:\n"]
            for a in out_of_stock:
                lines.append(f"🚨 OUT OF STOCK: {a['name']} ({a['category']})")
            for a in low_stock:
                lines.append(f"⚠️ LOW STOCK: {a['name']} — {a['quantity']} units left (threshold: {a['threshold']})")
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject='InventoryIQ — Stock Alert',
                Message="\n".join(lines)
            )

        if SQS_QUEUE_URL:
            sqs.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=json.dumps({
                    'event': 'insight_check',
                    'outOfStockCount': len(out_of_stock),
                    'lowStockCount': len(low_stock),
                    'totalProducts': len(items),
                    'estimatedValue': float(total_value)
                })
            )

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
                'Access-Control-Allow-Methods': 'OPTIONS,GET'
            },
            'body': json.dumps(insights)
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
