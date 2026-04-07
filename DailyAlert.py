import json
import boto3
import os
from decimal import Decimal
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr

# Initialize AWS service clients at module level (outside the handler)
# This is a Lambda best practice: clients are reused across warm invocations,
# avoiding the overhead of re-creating connections on every function call.
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

# Get the inventory table using the env var, falling back to 'InventoryIQ' if not set.
# This allows the same code to be deployed to different environments (dev/prod)
# without changing the code itself.
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

# SNS Topic ARN controls where alert emails/SMS are sent.
# If empty, SNS publish is skipped (useful for local testing).
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')

def lambda_handler(event, context):
    """
    Generates and sends a daily inventory stock report via SNS (email/SMS).

    This function is triggered on a scheduled basis (e.g., EventBridge cron rule)
    rather than by an API Gateway request. It scans ALL items across ALL users
    (no userID filter) and builds a formatted plain-text email report showing:
    - Overall inventory health score
    - Out-of-stock items that need immediate reordering
    - Low-stock items that should be restocked soon
    - Suggested reorder quantities for each problem item

    Unlike LowItemInsight.py (which is per-user and API-driven), this function
    is designed for a store administrator who wants a single daily summary.

    Event Parameters (optional, passed via EventBridge input):
    - store: Display name for the store in the email (default: 'Your Store')

    Response: 200 with summary counts and the email subject line
    """
    try:
        # ── STEP 1: FETCH ALL INVENTORY ITEMS ────────────────────────────────
        # Scan the entire table with no filter (all users, all items).
        # DynamoDB scans return at most 1MB of data per call, so we loop
        # using LastEvaluatedKey as a "bookmark" to fetch the next page.
        result = table.scan()
        items = result.get('Items', [])

        # Pagination loop: keep fetching until there are no more pages
        while 'LastEvaluatedKey' in result:
            result = table.scan(ExclusiveStartKey=result['LastEvaluatedKey'])
            items.extend(result.get('Items', []))

        # ── STEP 2: CLASSIFY ITEMS BY STOCK STATUS ────────────────────────────
        out_of_stock = []   # Items with quantity == 0 (critical)
        low_stock = []      # Items with 0 < quantity <= lowStockThreshold (warning)
        total_value = Decimal('0')  # Running total of (qty * price) across all items

        for item in items:
            # Convert DynamoDB types to Python numbers for math operations
            qty = int(item.get('quantity', 0))
            threshold = int(item.get('lowStockThreshold', 10))
            price = Decimal(str(item.get('price', 0)))

            # Accumulate total inventory value: quantity × unit price
            total_value += Decimal(str(qty)) * price

            if qty == 0:
                # OUT OF STOCK: needs immediate attention
                # Suggested reorder quantity: 2× threshold (replenish generously),
                # with a minimum of 10 units to avoid trivially small orders.
                out_of_stock.append({
                    'name': item.get('name', 'Unknown'),
                    'category': item.get('category', 'Uncategorized'),
                    'threshold': threshold,
                    'suggested': max(threshold * 2, 10)
                })
            elif qty <= threshold:
                # LOW STOCK: quantity is above zero but at or below the reorder threshold
                # Suggested reorder quantity: enough to reach 2× threshold,
                # but at least 'threshold' units to avoid another reorder too soon.
                low_stock.append({
                    'name': item.get('name', 'Unknown'),
                    'category': item.get('category', 'Uncategorized'),
                    'quantity': qty,
                    'threshold': threshold,
                    'suggested': max((threshold * 2) - qty, threshold)
                })

        # ── STEP 3: CALCULATE HEALTH SCORE ───────────────────────────────────
        total_products = len(items)
        at_risk = len(out_of_stock) + len(low_stock)
        healthy = total_products - at_risk

        # Health score starts at 100 and is penalized for stock problems:
        # -25 per out-of-stock item (critical, immediate action needed)
        # -10 per low-stock item (warning, plan to restock)
        # Clamped between 0 and 100. If no items exist, score stays 100.
        penalty = (len(out_of_stock) * 25) + (len(low_stock) * 10)
        health_score = max(0, min(100, 100 - penalty)) if total_products else 100

        # Map the numeric score to a human-readable label and ASCII progress bar
        if health_score >= 80:
            health_label = "HEALTHY"
            health_bar = "████████░░"   # 80% filled
        elif health_score >= 50:
            health_label = "MODERATE"
            health_bar = "█████░░░░░"   # 50% filled
        else:
            health_label = "CRITICAL"
            health_bar = "██░░░░░░░░"   # 20% filled

        # ── STEP 4: BUILD THE EMAIL BODY ─────────────────────────────────────
        # The report is a plain-text email formatted with ASCII box-drawing characters
        # so it displays correctly in any email client without HTML rendering.
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%A, %B %d, %Y")   # e.g. "Monday, April 06, 2026"
        time_str = now.strftime("%I:%M %p UTC")     # e.g. "09:00 AM UTC"

        lines = []

        # Header banner
        lines += [
            "╔══════════════════════════════════════════════════════╗",
            "║           INVENTORYIQ — DAILY STOCK REPORT           ║",
            "╚══════════════════════════════════════════════════════╝",
            "",
            f"  Date  : {date_str}",
            f"  Time  : {time_str}",
            # 'store' can be passed in via EventBridge input JSON, e.g. {"store": "Main Warehouse"}
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

        # Out-of-stock section: list each item with its suggested reorder quantity
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
            # Show a "none" placeholder so the email sections are always consistent
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "  🚨 OUT OF STOCK  — None",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]

        # Low-stock section: show each item's fill percentage and urgency level
        if low_stock:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"  ⚠️  LOW STOCK  ({len(low_stock)} item(s)) — REORDER SOON",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]
            for i in low_stock:
                # Percentage of threshold remaining: e.g. qty=3, threshold=10 → 30%
                pct = round((i['quantity'] / i['threshold']) * 100)
                # HIGH urgency if quantity is at or below half the threshold
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

        # All-clear message: only shown when there are zero stock issues
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

        # ── STEP 5: BUILD THE EMAIL SUBJECT LINE ─────────────────────────────
        # The subject adapts based on what problems exist so the recipient
        # can gauge urgency before even opening the email.
        subject = f"InventoryIQ Daily Report — {now.strftime('%b %d')} | "
        if out_of_stock:
            subject += f"🚨 {len(out_of_stock)} Out of Stock"
            if low_stock:
                subject += f", ⚠️ {len(low_stock)} Low"   # Append low-stock count if both exist
        elif low_stock:
            subject += f"⚠️ {len(low_stock)} Low Stock"
        else:
            subject += "✅ All Healthy"

        # ── STEP 6: PUBLISH TO SNS ────────────────────────────────────────────
        # SNS delivers the message to all confirmed subscriptions on the topic
        # (email addresses, SMS numbers, etc. configured in the AWS console).
        # If SNS_TOPIC_ARN is not set, this step is skipped silently.
        if SNS_TOPIC_ARN:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=subject,
                Message='\n'.join(lines)  # Join all lines into a single string
            )

        # Return a summary to the caller (EventBridge or manual test invocation)
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
