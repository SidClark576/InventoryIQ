import json
import boto3
import os
import uuid
from datetime import datetime
from decimal import Decimal
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
import time as _time
import _logging

FUNCTION_NAME = 'AddItem'

# Table names from environment with defaults
TABLE      = os.environ.get('DYNAMODB_TABLE',    'InventoryIQ')
TX_TABLE   = os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions')
IDEM_TABLE = os.environ.get('IDEMPOTENCY_TABLE',  'IdempotencyKeys')

# High-level resource for idempotency reads; low-level client for transactional writes
dynamodb   = boto3.resource('dynamodb')
ddb_client = boto3.client('dynamodb')
idem_table = dynamodb.Table(IDEM_TABLE)
serializer = TypeSerializer()


def _serialize(d):
    """Convert Python dict to DynamoDB low-level format (type descriptors)."""
    return {k: serializer.serialize(v) for k, v in d.items()}


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
    Creates a new inventory item and logs the transaction atomically.

    Sprint 3 changes:
    - userID read from x-iq-user header (injected by Proxy.py) — body fallback removed
    - version=1 set on every new item for optimistic locking
    - item write + transaction log written in single TransactWriteItems call
    - Idempotency-Key header support: replay returns original response body

    Flow:
    1. Parse request body and validate required fields (name)
    2. Check Idempotency-Key header — if seen before, replay cached response
    3. Read userID from x-iq-user header
    4. Generate UUID itemID, build item object with version=1
    5. TransactWriteItems: put item (condition: itemID must not exist) + put tx log
    6. Store idempotency record (24h TTL)
    7. Return 201 with created item

    Returns 409 if TransactionCanceledException (rare: UUID collision or idem conflict).
    """
    try:
        body    = json.loads(event.get('body', '{}'))
        headers = event.get('headers') or {}

        if not body.get('name'):
            return response(400, {'error': 'Product name is required'})

        # Idempotency: check for duplicate request before doing any writes
        idem_key = (
            headers.get('idempotency-key') or
            headers.get('Idempotency-Key') or
            ''
        ).strip()
        if idem_key:
            idem_resp = idem_table.get_item(Key={'key': idem_key})
            if idem_resp.get('Item'):
                # Replay: return the original successful response unchanged
                return response(200, json.loads(idem_resp['Item']['responseBody']))

        # Sprint 3: read userID from proxy-injected header; do NOT fall back to body
        user_id = (
            headers.get('x-iq-user') or
            headers.get('X-Iq-User') or
            ''
        ).strip()

        item_id   = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Build item with version=1 for optimistic locking (Sprint 3)
        item = {
            'itemID'           : item_id,
            'userID'           : user_id,
            'name'             : body.get('name'),
            'description'      : body.get('description', ''),
            'category'         : body.get('category', 'Uncategorized'),
            'quantity'         : int(body.get('quantity', 0)),
            'price'            : Decimal(str(body.get('price', 0))),
            'lowStockThreshold': int(body.get('lowStockThreshold', 10)),
            'version'          : 1,
            'createdAt'        : timestamp,
            'updatedAt'        : timestamp,
        }

        tx_item = {
            'transactionID' : str(uuid.uuid4()),
            'itemID'        : item_id,
            'itemName'      : item['name'],
            'userID'        : user_id,
            'changeType'    : 'create',
            'quantityBefore': 0,
            'quantityAfter' : item['quantity'],
            'quantityDelta' : item['quantity'],
            'notes'         : 'Item created',
            'createdAt'     : timestamp,
        }

        # Atomic write: item + transaction log in a single transaction
        # ConditionExpression prevents overwriting an existing item (UUID collision guard)
        ddb_client.transact_write_items(TransactItems=[
            {
                'Put': {
                    'TableName'          : TABLE,
                    'Item'               : _serialize(item),
                    'ConditionExpression': 'attribute_not_exists(itemID)',
                }
            },
            {
                'Put': {
                    'TableName': TX_TABLE,
                    'Item'     : _serialize(tx_item),
                }
            },
        ])

        # Store idempotency record after successful write (TTL = 24 hours)
        if idem_key:
            item_for_resp = {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()}
            resp_body = {'message': 'Item added successfully', 'item': item_for_resp}
            idem_table.put_item(Item={
                'key'         : idem_key,
                'responseBody': json.dumps(resp_body),
                'expiresAt'   : int(datetime.utcnow().timestamp()) + 86400,
            })

        item['price'] = float(item['price'])
        return response(201, {'message': 'Item added successfully', 'item': item})

    except ClientError as e:
        if e.response['Error']['Code'] == 'TransactionCanceledException':
            return response(409, {'error': 'Conflict — duplicate item ID or concurrent duplicate request'})
        raise
    except Exception as e:
        return response(500, {'error': str(e)})


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
