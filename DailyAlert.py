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
        # Scan all items
        result = table.scan()
        items = result.get('Items', [])
        while 'LastEvaluatedKey' in result:
            result = table.scan(ExclusiveStartKey=result['LastEvaluatedKey'])
            items.extend(result.get('Items', []))

        out_of_stock = []
        low_stock = []
        total_value = Decimal('0')

        for item in items:
            qty = int(item.get('quantity', 0))
            threshold = int(item.get('lowStockThreshold', 10))
            price = Decimal(str(item.get('price', 0)))
            total_value += Decimal(str(qty)) * price

            if qty == 0:
                out_of_stock.append({
                    'name': item.get('name', 'Unknown'),
                    'category': item.get('category', 'Uncategorized'),
                    'threshold': threshold,
                    'suggested': max(threshold * 2, 10)
                })
            elif qty <= threshold:
                low_stock.append({
                    'name': item.get('name', 'Unknown'),
                    'category': item.get('category', 'Uncategorized'),
                    'quantity': qty,
                    'threshold': threshold,
                    'suggested': max((threshold * 2) - qty, threshold)
                })

        total_products = len(items)
        at_risk = len(out_of_stock) + len(low_stock)
        healthy = total_products - at_risk

        # Calculate health score
        penalty = (len(out_of_stock) * 25) + (len(low_stock) * 10)
        health_score = max(0, min(100, 100 - penalty)) if total_products else 100

        if health_score >= 80:
            health_label = "HEALTHY"
            health_bar = "████████░░"
        elif health_score >= 50:
            health_label = "MODERATE"
            health_bar = "█████░░░░░"
        else:
            health_label = "CRITICAL"
            health_bar = "██░░░░░░░░"

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p UTC")

        # ── Build the email body ──────────────────────────────────────
        lines = []

        # Header
        lines += [
            "╔══════════════════════════════════════════════════════╗",
            "║           INVENTORYIQ — DAILY STOCK REPORT           ║",
            "╚══════════════════════════════════════════════════════╝",
            "",
            f"  Date  : {date_str}",
            f"  Time  : {time_str}",
            f"  Store : {event.get('store', 'Your Store')}",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "  INVENTORY HEALTH SCORE",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"  {health_bar}  {health_score}/100 — {health_label}",
            "",
            f"  Total Products  : {total_products}",
            f"  Healthy Items   : {healthy}",
            f"  At-Risk Items   : {at_risk}",
            f"  Est. Inv. Value : ${float(total_value):,.2f}",
            "",
        ]

        # Out of Stock Section
        if out_of_stock:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"  🚨 OUT OF STOCK  ({len(out_of_stock)} item(s)) — IMMEDIATE ACTION REQUIRED",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]
            for i in out_of_stock:
                lines += [
                    f"  ▸ {i['name']}",
                    f"    Category  : {i['category']}",
                    f"    Stock     : 0 units (EMPTY)",
                    f"    Reorder   : ~{i['suggested']} units suggested",
                    "",
                ]
        else:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "  🚨 OUT OF STOCK  — None",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]

        # Low Stock Section
        if low_stock:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"  ⚠️  LOW STOCK  ({len(low_stock)} item(s)) — REORDER SOON",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]
            for i in low_stock:
                pct = round((i['quantity'] / i['threshold']) * 100)
                urgency = "HIGH" if i['quantity'] <= max(1, i['threshold'] // 2) else "MEDIUM"
                lines += [
                    f"  ▸ {i['name']}",
                    f"    Category  : {i['category']}",
                    f"    Stock     : {i['quantity']} units  ({pct}% of threshold)  [{urgency}]",
                    f"    Threshold : {i['threshold']} units",
                    f"    Reorder   : ~{i['suggested']} units suggested",
                    "",
                ]
        else:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "  ⚠️  LOW STOCK  — None",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]

        # All clear message
        if not out_of_stock and not low_stock:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "  ✅ ALL STOCK LEVELS ARE HEALTHY",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
                "  No action required today. Great job keeping stock levels up!",
                "",
            ]

        # Footer
        lines += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "  This is an automated daily report from InventoryIQ.",
            "  Log in to your dashboard to take action.",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        subject = f"InventoryIQ Daily Report — {now.strftime('%b %d')} | "
        if out_of_stock:
            subject += f"🚨 {len(out_of_stock)} Out of Stock"
            if low_stock:
                subject += f", ⚠️ {len(low_stock)} Low"
        elif low_stock:
            subject += f"⚠️ {len(low_stock)} Low Stock"
        else:
            subject += "✅ All Healthy"

        if SNS_TOPIC_ARN:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=subject,
                Message='\n'.join(lines)
            )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Daily alert sent.',
                'outOfStock': len(out_of_stock),
                'lowStock': len(low_stock),
                'subject': subject
            })
        }

    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}