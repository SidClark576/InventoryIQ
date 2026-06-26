import json
import boto3
import os
from datetime import datetime, timezone
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
import time as _time
import _logging

FUNCTION_NAME = 'RestoreItem'

# Table name from environment with default
TABLE = os.environ.get('DYNAMODB_TABLE', 'InventoryIQ')

# Restore window: items deleted more than this many days ago cannot be restored
RESTORE_WINDOW_DAYS = int(os.environ.get('RESTORE_WINDOW_DAYS', '30'))

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
    Restores a soft-deleted inventory item within the 30-day restore window.

    Flow:
    1. Extract itemID from path
    2. Read existing item → 404 if not found
    3. Ownership check via x-iq-user header → 403 if mismatch
    4. Check item is actually deleted → 409 if not deleted
    5. Check deletedAt is within RESTORE_WINDOW_DAYS → 410 if too old
    6. TransactWriteItems: REMOVE deletedAt + deletedBy, SET updatedAt
    7. Return 200 with success message

    Returns 409 on TransactionCanceledException (item no longer in deleted state).

    Route: POST /items/{itemID}/restore
    Requires: valid session token (validated by Proxy.py)
    """
    try:
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        headers = event.get('headers') or {}

        # Read userID from proxy-injected header
        user_id = (
            headers.get('x-iq-user') or
            headers.get('X-Iq-User') or
            ''
        ).strip()

        # Read existing item
        existing_resp = table.get_item(Key={'itemID': item_id})
        existing = existing_resp.get('Item')
        if not existing:
            return response(404, {'error': 'Item not found'})

        # Ownership check: prevent cross-tenant restores
        if not user_id or existing.get('userID', '') != user_id:
            return response(403, {'error': 'Forbidden: item belongs to another user'})

        # Item must actually be soft-deleted to restore it
        deleted_at = existing.get('deletedAt')
        if not deleted_at:
            return response(409, {'error': 'Item is not deleted — nothing to restore'})

        # Enforce restore window
        try:
            deleted_dt = datetime.fromisoformat(deleted_at)
        except ValueError:
            deleted_dt = datetime.now(timezone.utc)  # Fallback: allow restore if timestamp is unparseable

        if deleted_dt.tzinfo is None:
            deleted_dt = deleted_dt.replace(tzinfo=timezone.utc)
        now_dt   = datetime.now(timezone.utc)
        age_days = (now_dt - deleted_dt).days

        if age_days > RESTORE_WINDOW_DAYS:
            return response(410, {
                'error': f'Item was deleted {age_days} days ago and cannot be restored (window: {RESTORE_WINDOW_DAYS} days)'
            })

        timestamp = datetime.now(timezone.utc).isoformat()

        # Restore: atomically remove deletedAt + deletedBy, update updatedAt
        # ConditionExpression ensures item is still in deleted state (not already restored)
        ddb_client.transact_write_items(TransactItems=[
            {
                'Update': {
                    'TableName'                : TABLE,
                    'Key'                      : {'itemID': {'S': item_id}},
                    'UpdateExpression'         : 'REMOVE deletedAt, deletedBy SET updatedAt = :ts',
                    'ConditionExpression'      : 'attribute_exists(deletedAt)',
                    'ExpressionAttributeValues': {':ts': serializer.serialize(timestamp)},
                }
            },
        ])

        return response(200, {'message': f'Item {item_id} restored successfully'})

    except ClientError as e:
        if e.response['Error']['Code'] == 'TransactionCanceledException':
            return response(409, {'error': 'Item is not in a deleted state — may have been restored already'})
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
