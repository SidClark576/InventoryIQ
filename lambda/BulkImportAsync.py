import json
import boto3
import os
import uuid
import csv
import io
import math
from datetime import datetime, timezone
import time as _time
import _logging

FUNCTION_NAME = 'BulkImportAsync'

TABLE = os.environ.get('DYNAMODB_TABLE', 'InventoryIQ')
TX_TABLE = os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions')
JOBS_TABLE = os.environ.get('IMPORT_JOBS_TABLE', 'ImportJobs')

CHUNK_SIZE = 25
UPDATE_EVERY_N_CHUNKS = 4  # flush progress every ~100 rows

dynamodb = boto3.resource('dynamodb')
ddb_client = boto3.client('dynamodb')
s3_client = boto3.client('s3')
serializer = boto3.dynamodb.types.TypeSerializer()

jobs_table = dynamodb.Table(JOBS_TABLE)


def _serialize(d):
    return {k: serializer.serialize(v) for k, v in d.items() if v is not None}


def _validate_row(row, idx):
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

    return {
        'name': name,
        'category': category,
        'quantity': quantity,
        'price': str(price),
        'lowStockThreshold': threshold,
        'barcode': barcode,
    }, None


def _write_chunk(valid_rows, user_id, timestamp):
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
            'notes': 'Bulk import (async)',
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


def _flush_progress(job_id, done_delta, failed_delta, new_errors):
    update_expr = 'ADD #done :dd, #failed :fd'
    expr_names = {'#done': 'done', '#failed': 'failed'}
    expr_values = {
        ':dd': {'N': str(done_delta)},
        ':fd': {'N': str(failed_delta)},
    }
    if new_errors:
        update_expr += ' SET #errs = list_append(if_not_exists(#errs, :empty), :new_errs)'
        expr_names['#errs'] = 'errors'
        expr_values[':empty'] = {'L': []}
        expr_values[':new_errs'] = {
            'L': [{'M': {k: {'S': str(v)} for k, v in e.items()}} for e in new_errors]
        }
    ddb_client.update_item(
        TableName=JOBS_TABLE,
        Key={'jobId': {'S': job_id}},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def lambda_handler(event, context):
    t0 = _time.time()
    res = _handle(event, context)
    _logging.log_json(
        event=event,
        function=FUNCTION_NAME,
        latency_ms=(_time.time() - t0) * 1000,
        status=res.get('statusCode', 200),
        is_error=res.get('statusCode', 200) >= 500,
    )
    return res


def _handle(event, context):
    """
    S3-triggered async CSV import.

    S3 key format: uploads/{userID}/{jobId}.csv
    Flow:
    1. Parse S3 event → bucket, key, userID, jobId
    2. GetObject → csv.DictReader
    3. Mark ImportJobs status='processing', total=N
    4. Validate rows; write in chunks of 25 via TransactWriteItems
    5. Flush progress every UPDATE_EVERY_N_CHUNKS chunks
    6. Finalize status='completed'|'failed' + finishedAt
    7. Delete S3 object (7-day lifecycle fallback)
    """
    try:
        record = event['Records'][0]
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        # key = uploads/{userID}/{jobId}.csv
        parts = key.split('/')
        if len(parts) != 3:
            return {'statusCode': 400, 'body': f'Unexpected key format: {key}'}

        _, user_id, filename = parts
        job_id = filename.replace('.csv', '')

        # Fetch CSV
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        csv_bytes = obj['Body'].read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(csv_bytes))
        all_rows = list(reader)
        total = len(all_rows)

        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()

        # Mark processing
        jobs_table.update_item(
            Key={'jobId': job_id},
            UpdateExpression='SET #status = :s, #total = :t, startedAt = :sa',
            ExpressionAttributeNames={'#status': 'status', '#total': 'total'},
            ExpressionAttributeValues={':s': 'processing', ':t': total, ':sa': timestamp},
        )

        # Validate all rows
        valid_rows = []
        validation_errors = []
        for idx, row in enumerate(all_rows, start=1):
            item, err = _validate_row(row, idx)
            if err:
                validation_errors.append(err)
            else:
                valid_rows.append(item)

        # Write in chunks
        num_chunks = math.ceil(len(valid_rows) / CHUNK_SIZE) if valid_rows else 0
        inserted = 0
        write_errors = []
        pending_done = 0
        pending_failed = 0
        pending_errors = []

        for i in range(num_chunks):
            chunk = valid_rows[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
            try:
                _write_chunk(chunk, user_id, timestamp)
                inserted += len(chunk)
                pending_done += len(chunk)
            except Exception as e:
                errs = [{'row': 'chunk', 'field': 'write', 'message': str(e)[:200]}] * len(chunk)
                write_errors.extend(errs)
                pending_failed += len(chunk)
                pending_errors.extend(errs)

            # Flush every N chunks or on final chunk
            if (i + 1) % UPDATE_EVERY_N_CHUNKS == 0 or i == num_chunks - 1:
                if pending_done > 0 or pending_failed > 0:
                    _flush_progress(job_id, pending_done, pending_failed, pending_errors)
                    pending_done = 0
                    pending_failed = 0
                    pending_errors = []

        # Flush validation errors into job record
        if validation_errors:
            _flush_progress(job_id, 0, len(validation_errors), validation_errors[:50])

        total_failed = len(validation_errors) + len(write_errors)
        final_status = 'completed' if inserted > 0 or total_failed < total else 'failed'

        jobs_table.update_item(
            Key={'jobId': job_id},
            UpdateExpression='SET #status = :s, finishedAt = :fa, #done = :d, #failed = :f',
            ExpressionAttributeNames={'#status': 'status', '#done': 'done', '#failed': 'failed'},
            ExpressionAttributeValues={
                ':s': final_status,
                ':fa': datetime.now(timezone.utc).isoformat(),
                ':d': inserted,
                ':f': total_failed,
            },
        )

        # Cleanup S3 object (best-effort; 7-day lifecycle handles stragglers)
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
        except Exception:
            pass

        return {'statusCode': 200, 'body': json.dumps({'inserted': inserted, 'failed': total_failed})}

    except Exception as e:
        return {'statusCode': 500, 'body': str(e)}
