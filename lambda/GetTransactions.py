import base64
import json
import os
import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from datetime import datetime, timezone
import time as _time
import _logging
import _org

FUNCTION_NAME = 'GetTransactions'

# Initialize DynamoDB with transactions table
# This table holds the audit log of all inventory changes
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

INDEX = 'orgID-createdAt-index'
MAX_ROWS = 200

# Standard CORS headers for GET requests
CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,GET'
}

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


def _since(event):
    """`since` query param as stored-format UTC ISO (createdAt is datetime.isoformat() +00:00), or None. Raises ValueError or OverflowError."""
    since = (event.get('queryStringParameters') or {}).get('since')
    if not since:
        return None
    dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def _paging(event, org_id):
    """(limit, cursor) from the query string; None when absent. Raises ValueError on a bad value
    or a cursor for another org (a start key is only ever for the caller's own org)."""
    qs = event.get('queryStringParameters') or {}
    limit, cursor = qs.get('limit'), qs.get('cursor')
    if limit is not None:
        limit = int(limit)
        if not 1 <= limit <= MAX_ROWS:
            raise ValueError('limit out of range')
    if cursor is not None:
        cursor = json.loads(base64.urlsafe_b64decode(cursor))
        if not isinstance(cursor, dict) or not all(isinstance(v, str) for v in cursor.values()):
            raise ValueError('bad cursor')
        if cursor.get('orgID', '') != org_id:
            raise ValueError('cursor is for another org')
    return limit, cursor


def _query(org_id, since, limit, cursor):
    """One page of orgID-createdAt-index, newest first: (rows, cursor or None). No limit = every row.
    Reads limit + 1 rows: DynamoDB sends a LastEvaluatedKey whenever Limit is hit, even on the last row."""
    cond = Key('orgID').eq(org_id)
    if since:
        cond = cond & Key('createdAt').gte(since)
    kwargs = {'IndexName': INDEX, 'KeyConditionExpression': cond, 'ScanIndexForward': False}
    if cursor:
        kwargs['ExclusiveStartKey'] = cursor
    want = limit + 1 if limit else None
    rows = []
    while True:
        if want:
            kwargs['Limit'] = want - len(rows)  # top up across 1 MB pages
        res = table.query(**kwargs)
        rows += res.get('Items', [])
        last = res.get('LastEvaluatedKey')
        if not last or (want and len(rows) >= want):
            return _trim(rows, limit)
        kwargs['ExclusiveStartKey'] = last


def _sort_key(row):
    return row.get('createdAt', ''), row.get('transactionID', '')


def _fallback(ctx, since, limit, cursor):
    """Same contract as _query without the new GSI (or for legacy no-org callers): orgID-index, sorted in memory."""
    rows = _org.list_scoped_items(table, ctx['org_id'], ctx['user_id'],
                                  Attr('createdAt').gte(since) if since else None)
    rows.sort(key=_sort_key, reverse=True)
    if cursor:
        rows = [r for r in rows if _sort_key(r) < _sort_key(cursor)]
    return _trim(rows, limit)


def _trim(rows, limit):
    """(first `limit` rows, cursor at the last one) when more rows follow, else (rows, None)."""
    if not limit or len(rows) <= limit:
        return rows, None
    rows = rows[:limit]
    return rows, {k: rows[-1][k] for k in ('transactionID', 'orgID', 'createdAt') if k in rows[-1]}


def _page(ctx, since, limit, cursor):
    if ctx['org_id']:
        try:
            return _query(ctx['org_id'], since, limit, cursor)
        except ClientError as e:  # only a missing orgID-createdAt-index falls back; throttles, AccessDenied surface
            if e.response['Error']['Code'] not in ('ValidationException', 'ResourceNotFoundException'):
                raise
    return _fallback(ctx, since, limit, cursor)


def _body(rows, last, paged):
    """Unpaged callers get the bare array as before; paged ones {items, nextCursor?}."""
    rows = [_logging.plain(r) for r in rows]  # DynamoDB returns Decimals; integers stay JSON integers (B4)
    if not paged:
        return rows
    body = {'items': rows}
    if last:
        body['nextCursor'] = base64.urlsafe_b64encode(json.dumps(last).encode()).decode()
    return body


def _handle(event, context):
    """
    Retrieves transaction history (audit log) for a specific user.

    Flow:
    1. Handle CORS preflight OPTIONS request
    2. Resolve the caller's org (require_member, viewer+)
    3. Query orgID-createdAt-index newest first (never a scan); if that GSI is not live yet,
       fall back to orgID-index and sort in memory
    4. Convert Decimals to JSON numbers

    Query Parameters:
    - since: Optional UTC ISO date. Only rows with createdAt >= since (key condition), and no 200 cap.
    - limit: Optional 1..200 page size. cursor: Optional `nextCursor` from the previous page.

    Response: with neither limit nor cursor, an array sorted newest-first (200 max unless `since` is given),
    as before. With either, {items, nextCursor}; nextCursor is absent on the last page.

    Transaction Types:
    - create: Item added to inventory
    - stock_in: Quantity increased (restocking)
    - stock_out: Quantity decreased (depletion)
    - update: Other fields changed (name, price, category, etc)
    - delete: Item removed from inventory
    """
    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    headers = event.get('headers') or {}
    ctx, err = _org.require_member(headers, minimum='viewer')
    if err:
        return err

    try:
        since = _since(event)
    except (ValueError, OverflowError):
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'since must be an ISO date'})}
    try:
        limit, cursor = _paging(event, ctx['org_id'])
    except ValueError:  # bad int, base64, UTF-8, JSON or org
        return {'statusCode': 400, 'headers': CORS,
                'body': json.dumps({'error': 'limit must be 1-200 and cursor a nextCursor from this list'})}
    paged = limit is not None or cursor is not None
    if not since:
        limit = limit or MAX_ROWS

    try:
        rows, last = _page(ctx, since, limit, cursor)
        return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(_body(rows, last, paged))}

    except Exception as e:
        return _logging.server_error(e, event, CORS)
