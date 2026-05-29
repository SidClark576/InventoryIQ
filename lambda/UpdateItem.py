import json
import uuid
import boto3
import os
from datetime import datetime, timezone
from decimal import Decimal
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
import time as _time
import _logging

FUNCTION_NAME = 'UpdateItem'

# Table names from environment with defaults
TABLE    = os.environ.get('DYNAMODB_TABLE',    'InventoryIQ')
TX_TABLE = os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions')

# High-level resource for reads; low-level client for transactional writes
dynamodb   = boto3.resource('dynamodb')
table      = dynamodb.Table(TABLE)
ddb_client = boto3.client('dynamodb')
serializer = TypeSerializer()


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


def _handle(event, context):
    """
    Updates an existing inventory item and logs the transaction atomically.

    Sprint 3 changes:
    - userID read from x-iq-user header (injected by Proxy.py) — body fallback removed
    - If-Match header required (integer version number); returns 428 if absent
    - Version must match stored version; returns 412 on mismatch
    - item update + transaction log written in single TransactWriteItems call
    - ConditionExpression enforces version match at DB level (guards concurrent requests)
    - ETag: <newVersion> returned in response headers
    - version incremented on every successful write

    Flow:
    1. Extract itemID from path, parse body + headers
    2. Read If-Match header → 428 if missing
    3. Read existing item → 404 if not found
    4. Ownership check via x-iq-user → 403 if mismatch
    5. Compare If-Match with stored version → 412 if mismatch (fast-fail before DB write)
    6. Build UpdateExpression for only the fields provided in body
    7. TransactWriteItems: update item (version condition) + put tx log
    8. Return 200 with reconstructed updated item + ETag header

    Returns 412 on TransactionCanceledException (concurrent version conflict).
    """
    try:
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        body      = json.loads(event.get('body', '{}'))
        headers   = event.get('headers') or {}
        timestamp = datetime.now(timezone.utc).isoformat()

        # Sprint 3: read userID from proxy-injected header; do NOT fall back to body
        user_id = (
            headers.get('x-iq-user') or
            headers.get('X-Iq-User') or
            ''
        ).strip()

        # Sprint 3: If-Match header required for all updates (optimistic locking)
        if_match_raw = (
            headers.get('if-match') or
            headers.get('If-Match') or
            None
        )
        if if_match_raw is None:
            return response(428, {'error': 'If-Match header required — include current item version'})

        try:
            client_version = int(if_match_raw)
        except (ValueError, TypeError):
            return response(400, {'error': 'If-Match must be an integer version number'})

        # Read existing item to verify ownership, version, and capture quantityBefore
        existing_resp = table.get_item(Key={'itemID': item_id})
        existing = existing_resp.get('Item')
        if not existing:
            return response(404, {'error': 'Item not found'})

        # Ownership check: prevent cross-tenant writes
        if not user_id or existing.get('userID', '') != user_id:
            return response(403, {'error': 'Forbidden: item belongs to another user'})

        # Fast-fail version check before touching the DB
        # TransactWriteItems ConditionExpression below handles the concurrent race case
        current_version = int(existing.get('version', 0))
        if client_version != current_version:
            return response(412, {
                'error': f'Version conflict: client sent {client_version}, item is at {current_version}. Re-fetch and retry.'
            })

        new_version = current_version + 1

        # Build UpdateExpression — only include fields present in the request body
        # '#ver' alias needed because 'version' is not reserved but consistent with '#nm' pattern
        update_parts = ['updatedAt = :ts', '#ver = :newv']
        expr_values  = {':ts': timestamp, ':newv': new_version, ':v': current_version}
        expr_names   = {'#ver': 'version'}

        if 'quantity' in body:
            update_parts.append('quantity = :qty')
            expr_values[':qty'] = int(body['quantity'])
        if 'name' in body:
            # 'name' is a DynamoDB reserved word — must use expression alias
            update_parts.append('#nm = :name')
            expr_values[':name'] = body['name']
            expr_names['#nm'] = 'name'
        if 'price' in body:
            update_parts.append('price = :price')
            expr_values[':price'] = Decimal(str(body['price']))
        if 'category' in body:
            update_parts.append('category = :cat')
            expr_values[':cat'] = body['category']
        if 'description' in body:
            update_parts.append('description = :desc')
            expr_values[':desc'] = body['description']
        if 'lowStockThreshold' in body:
            update_parts.append('lowStockThreshold = :lst')
            expr_values[':lst'] = int(body['lowStockThreshold'])
        if 'barcode' in body:
            update_parts.append('barcode = :barcode')
            expr_values[':barcode'] = body['barcode']

        update_expr     = 'SET ' + ', '.join(update_parts)
        ddb_expr_values = {k: serializer.serialize(v) for k, v in expr_values.items()}

        # Determine transaction type for audit log
        qty_before = int(existing.get('quantity', 0))
        qty_after  = int(body['quantity']) if 'quantity' in body else qty_before
        if   qty_after > qty_before: change_type = 'stock_in'
        elif qty_after < qty_before: change_type = 'stock_out'
        else:                         change_type = 'update'

        tx_item = {
            'transactionID' : str(uuid.uuid4()),
            'itemID'        : item_id,
            'itemName'      : body.get('name', existing.get('name', '')),
            'userID'        : user_id or existing.get('userID', ''),
            'changeType'    : change_type,
            'quantityBefore': qty_before,
            'quantityAfter' : qty_after,
            'quantityDelta' : qty_after - qty_before,
            'notes'         : body.get('notes', ''),
            'createdAt'     : timestamp,
        }

        # Atomic write: update item with version guard + log transaction
        # ConditionExpression '#ver = :v' catches concurrent writes that slipped past
        # the fast-fail check above (two simultaneous requests, same version)
        ddb_client.transact_write_items(TransactItems=[
            {
                'Update': {
                    'TableName'                : TABLE,
                    'Key'                      : {'itemID': {'S': item_id}},
                    'UpdateExpression'         : update_expr,
                    'ConditionExpression'      : '#ver = :v',
                    'ExpressionAttributeNames' : expr_names,
                    'ExpressionAttributeValues': ddb_expr_values,
                }
            },
            {
                'Put': {
                    'TableName': TX_TABLE,
                    'Item'     : {k: serializer.serialize(v) for k, v in tx_item.items()},
                }
            },
        ])

        # Reconstruct updated item for response
        # TransactWriteItems does not support ReturnValues, so we apply changes to existing
        updated = {k: float(v) if isinstance(v, Decimal) else v for k, v in existing.items()}
        updated['updatedAt'] = timestamp
        updated['version']   = new_version
        if 'quantity'          in body: updated['quantity']           = int(body['quantity'])
        if 'name'              in body: updated['name']               = body['name']
        if 'price'             in body: updated['price']              = float(body['price'])
        if 'category'          in body: updated['category']           = body['category']
        if 'description'       in body: updated['description']        = body['description']
        if 'lowStockThreshold' in body: updated['lowStockThreshold']  = int(body['lowStockThreshold'])
        if 'barcode'           in body: updated['barcode']            = body['barcode']

        return response(200, {'message': 'Item updated', 'item': updated},
                        extra_headers={'ETag': str(new_version)})

    except ClientError as e:
        if e.response['Error']['Code'] == 'TransactionCanceledException':
            # Concurrent write won the race — client must re-fetch and retry
            return response(412, {'error': 'Version conflict — item was modified concurrently. Re-fetch and retry.'})
        raise
    except Exception as e:
        return response(500, {'error': 'Internal Server Error'})


def response(status_code, body, extra_headers=None):
    headers = {
        'Content-Type'                : 'application/json',
        'Access-Control-Allow-Origin' : '*',
        'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE',
    }
    if extra_headers:
        headers.update(extra_headers)
    return {
        'statusCode': status_code,
        'headers'   : headers,
        'body'      : json.dumps(body),
    }
