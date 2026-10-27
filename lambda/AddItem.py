import json
import boto3
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
import time as _time
import _logging
import _org

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
        body, err = _logging.json_body(event)
        if err:
            return err
        headers = event.get('headers') or {}

        if not body.get('name'):
            return response(400, {'error': 'Product name is required'})
        nums = {}
        for name, integer, default in (('quantity', True, 0), ('price', False, Decimal(0)), ('lowStockThreshold', True, 10)):
            nums[name], err = _logging.number_field(body, name, integer, default)
            if err:
                return err

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

        ctx, err = _org.require_member(headers, minimum='editor')
        if err:
            return err
        user_id = ctx['user_id']
        org_id = ctx['org_id']

        item_id   = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # Build item with version=1 for optimistic locking (Sprint 3)
        item = {
            'itemID'           : item_id,
            'userID'           : user_id,
            'name'             : body.get('name'),
            'description'      : body.get('description', ''),
            'category'         : body.get('category', 'Uncategorized'),
            'supplierID'       : body.get('supplierID', ''),
            'quantity'         : nums['quantity'],
            'price'            : nums['price'],
            'lowStockThreshold': nums['lowStockThreshold'],
            'barcode'          : body.get('barcode', ''),
            'version'          : 1,
            'createdAt'        : timestamp,
            'updatedAt'        : timestamp,
        }
        if org_id:
            item['orgID'] = org_id
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
        if org_id:
            tx_item['orgID'] = org_id

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
        resp_body = {'message': 'Item added successfully', 'item': _logging.plain(item)}
        if idem_key:
            idem_table.put_item(Item={
                'key'         : idem_key,
                'responseBody': json.dumps(resp_body),
                'expiresAt'   : int(datetime.now(timezone.utc).timestamp()) + 86400,
            })

        return response(201, resp_body)

    except ClientError as e:
        if e.response['Error']['Code'] == 'TransactionCanceledException':
            return response(409, {'error': 'Conflict — duplicate item ID or concurrent duplicate request'})
        raise
    except Exception as e:
        _logging.capture_error(e)
        return response(500, {'error': 'Internal Server Error'})


response = _logging.response
