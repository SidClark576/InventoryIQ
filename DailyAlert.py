import json
import boto3
import os
from decimal import Decimal
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')

def lambda_handler(event, context):
    try:
        result = table.scan()
        items = result.get('Items', [])
        while 'LastEvaluatedKey' in result:
            result = table.scan(ExclusiveStartKey=result['LastEvaluatedKey'])
            items.extend(result.get('Items', []))

        out_of_stock = []
        low_stock = []

        for item in items:
            qty = int(item.get('quantity', 0))
            threshold = int(item.get('lowStockThreshold', 10))
            name = item.get('name', 'Unknown')
            category = item.get('category', 'Uncategorized')

            if qty == 0:
                out_of_stock.append(f"🚨 OUT OF STOCK: {name} ({category})")
            elif qty <= threshold:
                low_stock.append(f"⚠️  LOW STOCK: {name} ({category}) — {qty} units left (threshold: {threshold})")

        if not out_of_stock and not low_stock:
            return {'statusCode': 200, 'body': 'No alerts today.'}

        lines = [
            f"InventoryIQ — Daily Stock Alert",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"",
            f"{'='*40}",
        ]
        if out_of_stock:
            lines.append(f"\nOUT OF STOCK ({len(out_of_stock)} items):")
            lines.extend(out_of_stock)
        if low_stock:
            lines.append(f"\nLOW STOCK ({len(low_stock)} items):")
            lines.extend(low_stock)

        lines.append(f"\n{'='*40}")
        lines.append("Log in to InventoryIQ to take action.")

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f'InventoryIQ — Daily Stock Report ({datetime.now(timezone.utc).strftime("%b %d")})',
            Message='\n'.join(lines)
        )

        return {'statusCode': 200, 'body': f'Alert sent: {len(out_of_stock)} out, {len(low_stock)} low.'}

    except Exception as e:
        return {'statusCode': 500, 'body': str(e)}