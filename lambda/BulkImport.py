import json
import boto3
import os
import uuid
import math
from decimal import Decimal
from datetime import datetime, timezone
import time as _time
import _logging

FUNCTION_NAME = 'BulkImport'

TABLE = os.environ.get('DYNAMODB_TABLE', 'InventoryIQ')
TX_TABLE = os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions')
IDEM_TABLE = os.environ.get('IDEMPOTENCY_TABLE', 'IdempotencyKeys')
JOBS_TABLE = os.environ.get('IMPORT_JOBS_TABLE', 'ImportJobs')
IMPORT_BUCKET = os.environ.get('IMPORT_BUCKET', 'inventoryiq-imports')

MAX_SYNC_ROWS = 100
CHUNK_SIZE = 25
PRESIGN_TTL = 900  # 15 minutes
IDEM_TTL_SECONDS = 86400  # 24 hours

dynamodb = boto3.resource('dynamodb')
ddb_client = boto3.client('dynamodb')
s3_client = boto3.client('s3')
serializer = boto3.dynamodb.types.TypeSerializer()

jobs_table = dynamodb.Table(JOBS_TABLE)
idem_table = dynamodb.Table(IDEM_TABLE)


def _serialize(d):
    return {k: serializer.serialize(v) for k, v in d.items() if v is not None}


def _headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,x-api-key,x-iq-user,x-idempotency-key',
        'Access-Control-Allow-Methods': 'OPTIONS,GET,POST',
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


def _handle(event, context):
    method = event.get('httpMethod', 'GET').upper()
    path = event.get('path', '')
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}

    user_id = (headers.get('x-iq-user') or '').strip()
    if not user_id:
        return _err(401, 'Missing x-iq-user header')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': _headers(), 'body': ''}

    if method == 'GET' and 'presign' in path:
        return _handle_presign(event, user_id)

    if method == 'GET':
        return _handle_get_job(event, user_id)

    if method == 'POST':
        return _handle_sync_import(event, headers, user_id)

    return _err(405, f'Method {method} not allowed')


def _handle_presign(event, user_id):
    """Generate presigned S3 PUT URL for async CSV upload."""
    try:
        job_id = str(uuid.uuid4())
        s3_key = f'uploads/{user_id}/{job_id}.csv'

        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': IMPORT_BUCKET,
                'Key': s3_key,
                'ContentType': 'text/csv',
            },
            ExpiresIn=PRESIGN_TTL,
        )

        # Pre-create ImportJobs row so client can poll before S3 trigger fires
        now = datetime.now(timezone.utc)
        ttl = int(now.timestamp()) + (7 * 86400)
        jobs_table.put_item(Item={
            'jobId': job_id,
            'userID': user_id,
            'status': 'pending',
            'total': 0,
            'done': 0,
            'failed': 0,
            'errors': [],
            'createdAt': now.isoformat(),
            'ttl': ttl,
        })

        return _ok({'presignedUrl': presigned_url, 'jobId': job_id})

    except Exception as e:
        return _err(500, str(e))


def _handle_get_job(event, user_id):
    """Return ImportJobs status for a given jobId."""
    try:
        path_params = event.get('pathParameters') or {}
        job_id = (path_params.get('jobId') or '').strip()

        if not job_id:
            return _err(400, 'jobId required in path')

        resp = jobs_table.get_item(Key={'jobId': job_id})
        job = resp.get('Item')
        if not job:
            return _err(404, f'Job {job_id} not found')

        # Enforce ownership
        if job.get('userID') != user_id:
            return _err(403, 'Forbidden')

        # Decimal → float
        for k, v in job.items():
            if isinstance(v, Decimal):
                job[k] = float(v)

        return _ok(job)

    except Exception as e:
        return _err(500, str(e))


def _validate_row(row, idx):
    """
    Validate and normalize a single CSV/JSON row.
    Returns (item_dict, None) on success, (None, error_dict) on failure.
    """
    name = (row.get('name') or '').strip()
    if not name:
        return None, {'row': idx, 'field': 'name', 'message': 'name is required'}

    try:
        quantity = int(row.get('quantity', 0))
        if quantity < 0:
            raise ValueError
    except (ValueError, TypeError):
        return None, {'row': idx, 'field': 'quantity', 'message': 'must be non-negative integer'}

    try:
        price_raw = row.get('price', 0)
        price = float(price_raw) if price_raw != '' else 0.0
        if price < 0:
            raise ValueError
    except (ValueError, TypeError):
        return None, {'row': idx, 'field': 'price', 'message': 'must be non-negative number'}

    try:
        threshold_raw = row.get('lowStockThreshold', 0)
        threshold = int(threshold_raw) if threshold_raw != '' else 0
        if threshold < 0:
            raise ValueError
    except (ValueError, TypeError):
        return None, {'row': idx, 'field': 'lowStockThreshold', 'message': 'must be non-negative integer'}

    category = (row.get('category') or 'Uncategorized').strip() or 'Uncategorized'
    barcode = (row.get('barcode') or '').strip()

    item = {
        'name': name,
        'category': category,
        'quantity': quantity,
        'price': str(price),
        'lowStockThreshold': threshold,
        'barcode': barcode,
    }
    return item, None


def _write_chunk(valid_rows, user_id, timestamp):
    """Write a chunk of ≤25 items atomically via TransactWriteItems."""
    transact_items = []
    for row in valid_rows:
        item_id = str(uuid.uuid4())
        item = {
            'itemID': item_id,
            'name': row['name'],
            'description': '',
            'category': row['category'],
            'quantity': row['quantity'],
            'price': row['price'],
            'lowStockThreshold': row['lowStockThreshold'],
            'barcode': row.get('barcode', ''),
            'userID': user_id,
            'version': 1,
            'createdAt': timestamp,
            'updatedAt': timestamp,
        }
        tx_item = {
            'transactionID': str(uuid.uuid4()),
            'itemID': item_id,
            'itemName': row['name'],
            'userID': user_id,
            'changeType': 'create',
            'quantityBefore': 0,
            'quantityAfter': row['quantity'],
            'quantityDelta': row['quantity'],
            'notes': 'Bulk import',
            'createdAt': timestamp,
        }
        transact_items.append({
            'Put': {
                'TableName': TABLE,
                'Item': _serialize(item),
                'ConditionExpression': 'attribute_not_exists(itemID)',
            }
        })
        transact_items.append({
            'Put': {
                'TableName': TX_TABLE,
                'Item': _serialize(tx_item),
            }
        })
    ddb_client.transact_write_items(TransactItems=transact_items)


def _handle_sync_import(event, headers, user_id):
    """
    Sync import: parse JSON body rows, validate each, write in chunks of 25.
    Returns {inserted, failed, errors}.
    """
    try:
        body = json.loads(event.get('body') or '{}')
        rows = body.get('rows', [])

        if not isinstance(rows, list):
            return _err(400, "'rows' must be an array")

        if len(rows) > MAX_SYNC_ROWS:
            return _err(413, f'Too many rows ({len(rows)}). Use async upload for >100 rows.')

        # Idempotency
        idem_key = headers.get('x-idempotency-key', '').strip()
        if idem_key:
            idem_resp = idem_table.get_item(Key={'key': idem_key})
            existing = idem_resp.get('Item')
            if existing:
                return _ok(json.loads(existing['responseBody']))

        # Per-row validation
        valid_rows = []
        errors = []
        for idx, row in enumerate(rows, start=1):
            item, err = _validate_row(row, idx)
            if err:
                errors.append(err)
            else:
                valid_rows.append(item)

        # Write valid rows in chunks
        timestamp = datetime.now(timezone.utc).isoformat()
        inserted = 0
        chunk_errors = []
        num_chunks = math.ceil(len(valid_rows) / CHUNK_SIZE) if valid_rows else 0

        for i in range(num_chunks):
            chunk = valid_rows[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
            try:
                _write_chunk(chunk, user_id, timestamp)
                inserted += len(chunk)
            except Exception as e:
                for row in chunk:
                    chunk_errors.append({'row': 'unknown', 'field': 'write', 'message': str(e)})

        errors.extend(chunk_errors)
        result = {
            'inserted': inserted,
            'failed': len(errors),
            'errors': errors,
        }

        # Store idempotency record
        if idem_key:
            ttl = int(datetime.now(timezone.utc).timestamp()) + IDEM_TTL_SECONDS
            idem_table.put_item(Item={
                'key': idem_key,
                'responseBody': json.dumps(result),
                'ttl': ttl,
            })

        return _ok(result)

    except Exception as e:
        return _err(500, str(e))
