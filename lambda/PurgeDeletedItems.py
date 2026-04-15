import json
import boto3
import os
from datetime import datetime, timedelta, timezone
from boto3.dynamodb.conditions import Attr

# Table name from environment with default
TABLE             = os.environ.get('DYNAMODB_TABLE',  'InventoryIQ')
PURGE_AFTER_DAYS  = int(os.environ.get('PURGE_AFTER_DAYS', '30'))

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(TABLE)


def lambda_handler(event, context):
    """
    Scheduled Lambda: permanently hard-deletes items soft-deleted more than
    PURGE_AFTER_DAYS (default 30) days ago.

    Triggered by EventBridge daily schedule (e.g. rate(1 day)).

    Flow:
    1. Calculate cutoff timestamp (now - PURGE_AFTER_DAYS)
    2. Scan for items with deletedAt < cutoff (expired soft-deletes)
    3. Hard-delete each expired item from DynamoDB
    4. Log results (purged count + any errors) to CloudWatch

    Note: Table scan is acceptable for a scheduled daily job. In production
    with millions of items, add a GSI on deletedAt or use a DynamoDB Stream
    + Lambda approach to avoid full scans.
    """
    cutoff_dt  = datetime.now(timezone.utc) - timedelta(days=PURGE_AFTER_DAYS)
    cutoff_iso = cutoff_dt.isoformat()
    purged     = 0
    errors     = []

    scan_kwargs = {
        'FilterExpression': Attr('deletedAt').exists() & Attr('deletedAt').lt(cutoff_iso)
    }

    while True:
        result = table.scan(**scan_kwargs)

        for item in result.get('Items', []):
            try:
                table.delete_item(Key={'itemID': item['itemID']})
                purged += 1
                print(f"Purged item {item['itemID']} (deletedAt={item.get('deletedAt')})")
            except Exception as e:
                errors.append({'itemID': item['itemID'], 'error': str(e)})
                print(f"ERROR purging {item['itemID']}: {e}")

        if 'LastEvaluatedKey' not in result:
            break
        scan_kwargs['ExclusiveStartKey'] = result['LastEvaluatedKey']

    summary = {'purged': purged, 'errors': len(errors), 'cutoff': cutoff_iso}
    print(json.dumps(summary))

    return {
        'statusCode': 200,
        'body': json.dumps(summary)
    }
