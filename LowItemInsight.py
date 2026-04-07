import json
import boto3
import os
from decimal import Decimal
from collections import defaultdict
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr

# Initialize AWS services:
# - DynamoDB for reading inventory items
# - SNS for sending alerts via email/SMS
# - SQS for queueing stock events
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
sqs = boto3.client('sqs')

# Get table and service configurations from environment variables
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')  # Alert notifications
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL', '')  # Stock event queue

def lambda_handler(event, context):
    """
    Generates comprehensive inventory insights including stock analysis, risk assessment, and reorder recommendations.

    Flow:
    1. Extract userID and validate
    2. Scan all inventory items for the user
    3. Classify items as out-of-stock or low-stock
    4. Calculate inventory health metrics
    5. Identify reorder priorities based on risk scoring
    6. Generate smart recommendations
    7. Publish alerts via SNS (email notifications)
    8. Queue events to SQS for background processing
    9. Return comprehensive insights dashboard

    Query Parameters:
    - userID: Required. User email to analyze inventory for.

    Response: Comprehensive insights object containing:
    - summary: Overall health metrics
    - outOfStockItems: Critical items with 0 quantity
    - lowStockItems: Items below threshold
    - categoryBreakdown: Quantity totals by category
    - categoryRiskBreakdown: Risk assessment per category
    - topReorderPriorities: Top 5 items to reorder
    - recommendations: AI-generated actionable insights

    Health Score Calculation:
    - Base: 100
    - Penalty: -25 per out-of-stock item
    - Penalty: -10 per low-stock item
    - Range: 0-100
    """
    try:
        # Extract and validate userID
        params = event.get('queryStringParameters') or {}
        user_id = params.get('userID', '').strip()

        # Return empty insights if no userID (no inventory to analyze)
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

        # Scan all items for this user
        result = table.scan(FilterExpression=Attr('userID').eq(user_id))
        items = result.get('Items', [])

        # Pagination loop: handle DynamoDB scan limit (1MB per request)
        while 'LastEvaluatedKey' in result:
            result = table.scan(
                ExclusiveStartKey=result['LastEvaluatedKey'],
                FilterExpression=Attr('userID').eq(user_id)
            )
            items.extend(result.get('Items', []))

        # Initialize data structures for analysis
        low_stock = []  # Items with qty > 0 but <= threshold
        out_of_stock = []  # Items with qty == 0
        category_totals = defaultdict(int)  # Total quantity per category
        category_risk = defaultdict(lambda: {'total': 0, 'risk': 0})  # Risk metrics per category
        total_value = Decimal('0')  # Total inventory value
        reorder_candidates = []  # Items needing reorder, ranked by priority

        # Analyze each inventory item
        for item in items:
            # Extract key metrics with type conversions
            qty = int(item.get('quantity', 0))
            threshold = int(item.get('lowStockThreshold', 10))
            price = Decimal(str(item.get('price', 0)))
            category = item.get('category', 'Uncategorized')

            # Update category-level metrics
            category_totals[category] += qty
            category_risk[category]['total'] += 1  # Count of items in category
            total_value += Decimal(str(qty)) * price  # Add item value to total

            # Classify items as out-of-stock or low-stock based on quantity
            if qty == 0:
                # OUT OF STOCK: Highest priority, needs immediate reorder
                category_risk[category]['risk'] += 1
                # Priority score: higher threshold = higher priority
                priority_score = (threshold + 1) * 3
                reorder_candidates.append({
                    'itemID': item.get('itemID'),
                    'name': item.get('name', 'Unknown Item'),
                    'category': category,
                    'currentQuantity': qty,
                    'threshold': threshold,
                    'priorityScore': priority_score,
                    'suggestedOrderQuantity': max(threshold * 2, 10),  # Suggest 2x threshold, min 10
                    'urgency': 'critical'
                })
                out_of_stock.append({
                    'itemID': item.get('itemID'),
                    'name': item.get('name'),
                    'category': category,
                    'alert': '🚨 OUT OF STOCK — reorder immediately'
                })
            elif qty <= threshold:
                # LOW STOCK: Quantity is at or below reorder threshold
                category_risk[category]['risk'] += 1
                # Priority score based on shortage severity
                shortage = max(threshold - qty, 0)
                priority_score = shortage + threshold  # More shortage = higher priority
                reorder_candidates.append({
                    'itemID': item.get('itemID'),
                    'name': item.get('name', 'Unknown Item'),
                    'category': category,
                    'currentQuantity': qty,
                    'threshold': threshold,
                    'priorityScore': priority_score,
                    'suggestedOrderQuantity': max((threshold * 2) - qty, threshold),  # 2x-current or threshold
                    'urgency': 'high' if qty <= max(1, threshold // 2) else 'medium'  # Critical if at half threshold
                })
                low_stock.append({
                    'itemID': item.get('itemID'),
                    'name': item.get('name'),
                    'quantity': qty,
                    'threshold': threshold,
                    'category': category,
                    'alert': f'⚠️ Low stock: only {qty} units left (threshold: {threshold})'
                })

        # Sort reorder candidates by priority score (highest first) and take top 5
        reorder_candidates.sort(key=lambda x: x['priorityScore'], reverse=True)
        top_reorder = reorder_candidates[:5]

        # Calculate summary metrics
        total_products = len(items)
        at_risk_count = len(out_of_stock) + len(low_stock)

        # Health score calculation: starts at 100, penalized for risk items
        # Out-of-stock is more critical (-25 per item) than low-stock (-10 per item)
        out_of_stock_penalty = len(out_of_stock) * 25
        low_stock_penalty = len(low_stock) * 10
        base_health = 100 - out_of_stock_penalty - low_stock_penalty
        # Clamp score to 0-100 range; perfect 100 if no items
        health_score = max(0, min(100, base_health)) if total_products else 100

        # Calculate risk percentage per category
        # This shows which categories have the most stock issues
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
        # Sort by risk percentage (highest risk first)
        category_risk_breakdown.sort(key=lambda x: x['riskPercent'], reverse=True)

        # Generate actionable recommendations based on inventory state
        recommendations = []
        if out_of_stock:
            recommendations.append(f"🔴 {len(out_of_stock)} item(s) are completely out of stock. Place orders immediately.")
        if low_stock:
            recommendations.append(f"🟡 {len(low_stock)} item(s) are running low. Consider restocking soon.")
        if top_reorder:
            # Highlight the single highest priority item
            recommendations.append(f"📌 Prioritize reorder for {top_reorder[0]['name']} in {top_reorder[0]['category']}.")
        if not items:
            recommendations.append("📦 No inventory found. Start by adding products.")
        if not out_of_stock and not low_stock and items:
            recommendations.append("✅ All stock levels are healthy!")

        # Assemble comprehensive insights dashboard
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
            'categoryBreakdown': dict(category_totals),  # {category: total_qty}
            'categoryRiskBreakdown': category_risk_breakdown,  # [category risk metrics]
            'topReorderPriorities': top_reorder,  # Top 5 by priority score
            'recommendations': recommendations,  # AI-generated insights
            'generatedAt': datetime.now(timezone.utc).isoformat()
        }

        # Publish alerts via SNS if there are items needing attention
        # This sends email/SMS notifications to configured recipients
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

        # Queue event to SQS for background processing
        # This decouples insights generation from further processing (e.g., reports, webhooks)
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

        # Return comprehensive insights to frontend dashboard
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
        # Return error with CORS headers
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
