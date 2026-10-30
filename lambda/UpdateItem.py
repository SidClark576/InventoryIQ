import json
import uuid
import boto3
import os
from datetime import datetime, timezone
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
import time as _time
import _logging
import _org

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

        body, err = _logging.json_body(event)
        if err:
            return err
        headers   = event.get('headers') or {}
        timestamp = datetime.now(timezone.utc).isoformat()

        ctx, err = _org.require_member(headers, minimum='editor')
        if err:
            return err
        user_id = ctx['user_id']
        org_id = ctx['org_id']

        changes = {k: body[k] for k in _TEXT_FIELDS if k in body}
        for name, integer in _NUMBER_FIELDS:
            value, err = _logging.number_field(body, name, integer=integer)
            if err:
                return err
            if name in body:
                changes[name] = value
        expires_at, err = _logging.date_field(body, 'expiresAt')
        if err:
            return err
        if expires_at is not None:
            changes['expiresAt'] = expires_at

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

        if not _org.item_in_scope(existing, org_id, user_id):
            return response(403, {'error': 'Forbidden: item is outside this organization'})
        if existing.get('deletedAt'):
            return response(410, ITEM_DELETED)

        # Fast-fail version check before touching the DB
        # TransactWriteItems ConditionExpression below handles the concurrent race case
        current_version = int(existing.get('version', 0))
        if client_version != current_version:
            return _conflict(existing,
                             f'Version conflict: client sent {client_version}, item is at {current_version}. Re-fetch and retry.')

        new_version = current_version + 1

        # Build UpdateExpression — only the fields present in the body; every field aliased (B9 '#nm' pattern)
        update_parts = ['updatedAt = :ts', '#ver = :newv']
        expr_values  = {':ts': timestamp, ':newv': new_version, ':v': current_version}
        expr_names   = {'#ver': 'version'}
        for field, value in changes.items():
            update_parts.append(f'#{field} = :{field}')
            expr_names[f'#{field}'] = field
            expr_values[f':{field}'] = value

        update_expr     = 'SET ' + ', '.join(update_parts)
        ddb_expr_values = {k: serializer.serialize(v) for k, v in expr_values.items()}

        # Determine transaction type for audit log
        qty_before = int(existing.get('quantity', 0))
        qty_after  = changes.get('quantity', qty_before)
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
        if org_id:
            tx_item['orgID'] = org_id

        # Atomic write: update item with version guard + log transaction
        # ConditionExpression '#ver = :v' catches concurrent writes that slipped past
        # the fast-fail check above (two simultaneous requests, same version)
        ddb_client.transact_write_items(TransactItems=[
            {
                'Update': {
                    'TableName'                : TABLE,
                    'Key'                      : {'itemID': {'S': item_id}},
                    'UpdateExpression'         : update_expr,
                    'ConditionExpression'      : '#ver = :v AND attribute_not_exists(deletedAt)',
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
        updated = _logging.plain({**existing, **changes, 'updatedAt': timestamp, 'version': new_version})

        return response(200, {'message': 'Item updated', 'item': updated},
                        extra_headers={'ETag': str(new_version)})

    except ClientError as e:
        if e.response['Error']['Code'] == 'TransactionCanceledException':
            # Concurrent write won the race — client must re-fetch and retry
            current = table.get_item(Key={'itemID': item_id}).get('Item') or {}
            if current.get('deletedAt'):
                return response(410, ITEM_DELETED)
            return _conflict(current, 'Version conflict — item was modified concurrently. Re-fetch and retry.')
        raise
    except Exception as e:
        _logging.capture_error(e, event=event)
        return response(500, {'error': 'Internal Server Error'})


response = _logging.response
ITEM_DELETED = {'error': 'Item has been deleted', 'code': 'ITEM_DELETED'}
_TEXT_FIELDS = ('name', 'category', 'description', 'barcode', 'supplierID')
_NUMBER_FIELDS = (('quantity', True), ('price', False), ('lowStockThreshold', True))


def _conflict(current, message):
    """412 with the current row and its version as ETag, so the client can merge without a re-fetch."""
    version = int(current.get('version', 0))
    return response(412, {'error': message, 'item': _logging.plain(current)}, extra_headers={'ETag': str(version)})
