import json
import boto3
import os
import math
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key, Attr
import time as _time
import _logging

FUNCTION_NAME = 'Forecast'

TABLE = os.environ.get('DYNAMODB_TABLE', 'InventoryIQ')
TX_TABLE = os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions')

MIN_SAMPLE_SIZE = 3
WINDOW_DAYS = 90
WMA_WEIGHTS = {30: 0.5, 60: 0.3, 90: 0.2}

dynamodb = boto3.resource('dynamodb')
items_table = dynamodb.Table(TABLE)
tx_table = dynamodb.Table(TX_TABLE)


def _headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,x-api-key,x-iq-user',
        'Access-Control-Allow-Methods': 'OPTIONS,GET',
    }


def _ok(body):
    return {'statusCode': 200, 'headers': _headers(), 'body': json.dumps(body)}


def _err(status, msg):
    return {'statusCode': status, 'headers': _headers(), 'body': json.dumps({'error': msg})}


def lambda_handler(event, context):
    t0 = _time.time()
    res = _handle(event, context)
    _logging.log_json(
        event=event,
        function=FUNCTION_NAME,
        latency_ms=(_time.time() - t0) * 1000,
        status=res.get('statusCode'),
        is_error=res.get('statusCode', 200) >= 500,
    )
    return res


def _scan_transactions(user_id, cutoff_iso):
    """Paginated scan of InventoryTransactions filtered by userID + changeType='stock_out' + createdAt>=cutoff."""
    filter_expr = (
        Attr('userID').eq(user_id) &
        Attr('changeType').eq('stock_out') &
        Attr('createdAt').gte(cutoff_iso)
    )
    result = tx_table.scan(FilterExpression=filter_expr)
    items = result.get('Items', [])
    while 'LastEvaluatedKey' in result:
        result = tx_table.scan(
            FilterExpression=filter_expr,
            ExclusiveStartKey=result['LastEvaluatedKey'],
        )
        items.extend(result.get('Items', []))
    return items


def _query_current_items(user_id):
    """Query InventoryIQ via userID-index GSI, excluding soft-deleted items."""
    result = items_table.query(
        IndexName='userID-index',
        KeyConditionExpression=Key('userID').eq(user_id),
        FilterExpression=Attr('deletedAt').not_exists(),
    )
    items = result.get('Items', [])
    while 'LastEvaluatedKey' in result:
        result = items_table.query(
            IndexName='userID-index',
            KeyConditionExpression=Key('userID').eq(user_id),
            FilterExpression=Attr('deletedAt').not_exists(),
            ExclusiveStartKey=result['LastEvaluatedKey'],
        )
        items.extend(result.get('Items', []))
    return items


def _wma(tx_for_item, now):
    """
    Compute Weighted Moving Average daily burn rate.

    WMA weights: 30d=0.5, 60d=0.3, 90d=0.2
    dailyBurn_Nd = total_qty_out_in_last_Nd / N
    WMA = 0.5*burn30 + 0.3*burn60 + 0.2*burn90
    """
    cutoffs = {
        30: (now - timedelta(days=30)).replace(tzinfo=timezone.utc),
        60: (now - timedelta(days=60)).replace(tzinfo=timezone.utc),
        90: (now - timedelta(days=90)).replace(tzinfo=timezone.utc),
    }

    qty_by_window = {30: 0.0, 60: 0.0, 90: 0.0}

    for tx in tx_for_item:
        created_at = tx.get('createdAt', '')
        try:
            tx_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except Exception:
            continue
        delta = abs(float(tx.get('quantityDelta', 0)))
        for window_days, cutoff_dt in cutoffs.items():
            if tx_time >= cutoff_dt:
                qty_by_window[window_days] += delta

    burn_rates = {w: qty_by_window[w] / w for w in [30, 60, 90]}
    wma = sum(WMA_WEIGHTS[w] * burn_rates[w] for w in [30, 60, 90])
    return wma


def _handle(event, context):
    """
    Demand Forecasting via Weighted Moving Average on stock_out transactions.

    Flow:
    1. Extract userID from x-iq-user header (Proxy-injected)
    2. Scan InventoryTransactions: userID + changeType='stock_out' + createdAt>=90d ago
    3. Query current InventoryIQ items via userID-index GSI
    4. Group transactions by itemID; compute WMA per item
    5. Skip items with sampleSize < MIN_SAMPLE_SIZE
    6. Return {forecasts:[...]} sorted by urgency (lowest daysUntilStockout first)
    """
    try:
        headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
        user_id = (headers.get('x-iq-user') or '').strip()
        if not user_id:
            return _err(401, 'Missing x-iq-user header')

        now = datetime.now(timezone.utc)
        cutoff_iso = (now - timedelta(days=WINDOW_DAYS)).isoformat()

        tx_items = _scan_transactions(user_id, cutoff_iso)
        current_items = _query_current_items(user_id)

        # Build item lookup: itemID → {name, quantity}
        item_lookup = {}
        for item in current_items:
            item_id = item.get('itemID', '')
            if not item_id:
                continue
            qty = item.get('quantity', 0)
            if isinstance(qty, Decimal):
                qty = float(qty)
            item_lookup[item_id] = {
                'name': item.get('name', ''),
                'quantity': int(qty),
            }

        # Group transactions by itemID
        tx_by_item = {}
        for tx in tx_items:
            item_id = tx.get('itemID', '')
            if not item_id:
                continue
            tx_by_item.setdefault(item_id, []).append(tx)

        forecasts = []
        last_updated = now.isoformat()

        for item_id, txs in tx_by_item.items():
            sample_size = len(txs)
            if sample_size < MIN_SAMPLE_SIZE:
                continue

            item_info = item_lookup.get(item_id)
            if not item_info:
                continue

            daily_burn = _wma(txs, now)
            if daily_burn <= 0:
                continue

            current_qty = item_info['quantity']
            days_until_stockout = current_qty / daily_burn
            confidence = min(1.0, sample_size / 14)
            suggested_threshold = math.ceil(daily_burn * 7)

            forecasts.append({
                'itemID': item_id,
                'name': item_info['name'],
                'dailyBurn': round(daily_burn, 4),
                'daysUntilStockout': round(days_until_stockout, 1),
                'confidence': round(confidence, 2),
                'suggestedThreshold': suggested_threshold,
                'method': 'WMA',
                'sampleSize': sample_size,
                'windowDays': WINDOW_DAYS,
                'lastUpdated': last_updated,
            })

        forecasts.sort(key=lambda x: x['daysUntilStockout'])

        return _ok({'forecasts': forecasts})

    except Exception as e:
        return _err(500, str(e))
