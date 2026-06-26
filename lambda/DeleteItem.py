import json
import uuid
import boto3
import os
from datetime import datetime, timezone
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
import time as _time
import _logging

FUNCTION_NAME = 'DeleteItem'

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
    Soft-deletes an inventory item and logs the transaction atomically.

    Sprint 3 changes:
    - Hard delete replaced with soft delete: sets deletedAt + deletedBy on item
    - userID read from x-iq-user header (injected by Proxy.py) — query param fallback removed
    - Soft-delete update + transaction log written in single TransactWriteItems call
    - ConditionExpression prevents double-deletion
    - GetAllItems filters out items with deletedAt (they're hidden, not gone)
    - Items can be restored within 30 days via POST /items/{id}/restore
    - PurgeDeletedItems Lambda permanently deletes items after 30 days

    Flow:
    1. Extract itemID from path
    2. Read existing item → 404 if not found; 410 if already soft-deleted
    3. Ownership check via x-iq-user → 403 if mismatch
    4. TransactWriteItems: set deletedAt/deletedBy (condition: not already deleted) + put tx log
    5. Return 200 with success message

    Returns 409 on TransactionCanceledException (concurrent delete race).
    """
    try:
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        headers = event.get('headers') or {}

        # Sprint 3: read userID from proxy-injected header; do NOT fall back to query params
        user_id = (
            headers.get('x-iq-user') or
            headers.get('X-Iq-User') or
            ''
        ).strip()

        # Read existing item for ownership check and audit trail
        existing_resp = table.get_item(Key={'itemID': item_id})
        existing = existing_resp.get('Item')
        if not existing:
            return response(404, {'error': 'Item not found'})

        # Ownership check: prevent cross-tenant deletes
        if not user_id or existing.get('userID', '') != user_id:
            return response(403, {'error': 'Forbidden: item belongs to another user'})

        # Already soft-deleted — return 410 Gone
        if existing.get('deletedAt'):
            return response(410, {'error': 'Item already deleted'})

        timestamp = datetime.now(timezone.utc).isoformat()
        qty       = int(existing.get('quantity', 0))

        tx_item = {
            'transactionID' : str(uuid.uuid4()),
            'itemID'        : item_id,
            'itemName'      : existing.get('name', ''),
            'userID'        : existing.get('userID', ''),
            'changeType'    : 'delete',
            'quantityBefore': qty,
            'quantityAfter' : 0,
            'quantityDelta' : -qty,  # Negative delta represents removal
            'notes'         : 'Item soft-deleted',
            'createdAt'     : timestamp,
        }

        # Soft delete: stamp deletedAt + deletedBy atomically with transaction log
        # ConditionExpression prevents race where two requests both try to delete
        ddb_client.transact_write_items(TransactItems=[
            {
                'Update': {
                    'TableName'                : TABLE,
                    'Key'                      : {'itemID': {'S': item_id}},
                    'UpdateExpression'         : 'SET deletedAt = :da, deletedBy = :db',
                    'ConditionExpression'      : 'attribute_not_exists(deletedAt)',
                    'ExpressionAttributeValues': {
                        ':da': serializer.serialize(timestamp),
                        ':db': serializer.serialize(user_id),
                    },
                }
            },
            {
                'Put': {
                    'TableName': TX_TABLE,
                    'Item'     : {k: serializer.serialize(v) for k, v in tx_item.items()},
                }
            },
        ])

        return response(200, {'message': f'Item {item_id} deleted successfully'})

    except ClientError as e:
        if e.response['Error']['Code'] == 'TransactionCanceledException':
            return response(409, {'error': 'Conflict — item may have been deleted concurrently'})
        raise
    except Exception as e:
        _logging.capture_error(e)
        return response(500, {'error': 'Internal Server Error'})


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type'                : 'application/json',
            'Access-Control-Allow-Origin' : '*',
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE',
        },
        'body': json.dumps(body),
    }
