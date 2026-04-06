import json
import boto3
import os
from decimal import Decimal
from collections import defaultdict
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
sqs = boto3.client('sqs')

table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL', '')

def lambda_handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        user_id = params.get('userID', '').strip()

        if not user_id:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
                    'Access-Control-Allow-Methods': 'OPTIONS,GET'
                },
                'body': json.dumps({
                    'summary': {
                        'totalProducts': 0, 'outOfStockCount': 0, 'lowStockCount': 0,
                        'atRiskCount': 0, 'healthScore': 100, 'estimatedInventoryValue': 0
                    },
                    'outOfStockItems': [], 'lowStockItems': [], 'categoryBreakdown': {},
                    'categoryRiskBreakdown': [], 'topReorderPriorities': [],
                    'recommendations': ['📦 No inventory found. Start by adding products.'],
                    'generatedAt': datetime.now(timezone.utc).isoformat()
                })
            }

        result = table.scan(FilterExpression=Attr('userID').eq(user_id))
        items = result.get('Items', [])

        while 'LastEvaluatedKey' in result:
            result = table.scan(
                ExclusiveStartKey=result['LastEvaluatedKey'],
                FilterExpression=Attr('userID').eq(user_id)
            )
            items.extend(result.get('Items', []))

        low_stock = []
        out_of_stock = []
        category_totals = defaultdict(int)
        category_risk = defaultdict(lambda: {'total': 0, 'risk': 0})
        total_value = Decimal('0')
        reorder_candidates = []

        for item in items:
            qty = int(item.get('quantity', 0))
            threshold = int(item.get('lowStockThreshold', 10))
            price = Decimal(str(item.get('price', 0)))
            category = item.get('category', 'Uncategorized')

            category_totals[category] += qty
            category_risk[category]['total'] += 1
            total_value += Decimal(str(qty)) * price

            if qty == 0:
                category_risk[category]['risk'] += 1
                priority_score = (threshold + 1) * 3
                reorder_candidates.append({
                    'itemID': item.get('itemID'),
                    'name': item.get('name', 'Unknown Item'),
                    'category': category,
                    'currentQuantity': qty,
                    'threshold': threshold,
                    'priorityScore': priority_score,
                    'suggestedOrderQuantity': max(threshold * 2, 10),
                    'urgency': 'critical'
                })
                out_of_stock.append({
                    'itemID': item.get('itemID'),
                    'name': item.get('name'),
                    'category': category,
                    'alert': '🚨 OUT OF STOCK — reorder immediately'
                })
            elif qty <= threshold:
                category_risk[category]['risk'] += 1
                shortage = max(threshold - qty, 0)
                priority_score = shortage + threshold
                reorder_candidates.append({
                    'itemID': item.get('itemID'),
                    'name': item.get('name', 'Unknown Item'),
                    'category': category,
                    'currentQuantity': qty,
                    'threshold': threshold,
                    'priorityScore': priority_score,
                    'suggestedOrderQuantity': max((threshold * 2) - qty, threshold),
                    'urgency': 'high' if qty <= max(1, threshold // 2) else 'medium'
                })
                low_stock.append({
                    'itemID': item.get('itemID'),
                    'name': item.get('name'),
                    'quantity': qty,
                    'threshold': threshold,
                    'category': category,
                    'alert': f'⚠️ Low stock: only {qty} units left (threshold: {threshold})'
                })

        reorder_candidates.sort(key=lambda x: x['priorityScore'], reverse=True)
        top_reorder = reorder_candidates[:5]

        total_products = len(items)
        at_risk_count = len(out_of_stock) + len(low_stock)
        out_of_stock_penalty = len(out_of_stock) * 25
        low_stock_penalty = len(low_stock) * 10
        base_health = 100 - out_of_stock_penalty - low_stock_penalty
        health_score = max(0, min(100, base_health)) if total_products else 100

        category_risk_breakdown = []
        for category, stats in category_risk.items():
            total = stats['total']
            risk = stats['risk']
            risk_percent = round((risk / total) * 100, 2) if total else 0
            category_risk_breakdown.append({
                'category': category,
                'totalItems': total,
                'atRiskItems': risk,
                'riskPercent': risk_percent
            })
        category_risk_breakdown.sort(key=lambda x: x['riskPercent'], reverse=True)

        recommendations = []
        if out_of_stock:
            recommendations.append(f"🔴 {len(out_of_stock)} item(s) are completely out of stock. Place orders immediately.")
        if low_stock:
            recommendations.append(f"🟡 {len(low_stock)} item(s) are running low. Consider restocking soon.")
        if top_reorder:
            recommendations.append(f"📌 Prioritize reorder for {top_reorder[0]['name']} in {top_reorder[0]['category']}.")
        if not items:
            recommendations.append("📦 No inventory found. Start by adding products.")
        if not out_of_stock and not low_stock and items:
            recommendations.append("✅ All stock levels are healthy!")

        insights = {
            'summary': {
                'totalProducts': total_products,
                'outOfStockCount': len(out_of_stock),
                'lowStockCount': len(low_stock),
                'atRiskCount': at_risk_count,
                'healthScore': health_score,
                'estimatedInventoryValue': float(total_value)
            },
            'outOfStockItems': out_of_stock,
            'lowStockItems': low_stock,
            'categoryBreakdown': dict(category_totals),
            'categoryRiskBreakdown': category_risk_breakdown,
            'topReorderPriorities': top_reorder,
            'recommendations': recommendations,
            'generatedAt': datetime.now(timezone.utc).isoformat()
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
