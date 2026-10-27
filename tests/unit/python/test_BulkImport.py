"""AC4: presign stores orgID on the job; async import stamps it on items and tx rows; prices stored as numbers."""
import json
from decimal import Decimal

import boto3
import pytest

HEADERS = {'x-iq-user': 'a@b.co', 'x-iq-org': 'o1'}


def test_presign_stores_org_on_job(load, ddb):
    res = load('BulkImport').lambda_handler(
        {'httpMethod': 'GET', 'path': '/import/presign', 'headers': HEADERS}, None)
    assert res['statusCode'] == 200
    job = ddb.Table('ImportJobs').get_item(Key={'jobId': json.loads(res['body'])['jobId']})['Item']
    assert job['orgID'] == 'o1' and job['userID'] == 'a@b.co'


def test_async_import_stamps_org_and_numeric_price(load, ddb):
    s3 = boto3.client('s3')
    s3.create_bucket(Bucket='imports-test')
    s3.put_object(Bucket='imports-test', Key='uploads/a@b.co/j1.csv', Body=b'name,quantity,price\nRice,5,9.5\n')
    ddb.Table('ImportJobs').put_item(Item={'jobId': 'j1', 'userID': 'a@b.co', 'orgID': 'o1', 'status': 'pending'})
    load('BulkImportAsync').lambda_handler(
        {'Records': [{'s3': {'bucket': {'name': 'imports-test'}, 'object': {'key': 'uploads/a@b.co/j1.csv'}}}]}, None)
    item = ddb.Table('InventoryIQ').scan()['Items'][0]
    tx = ddb.Table('InventoryTransactions').scan()['Items'][0]
    assert item['orgID'] == 'o1' and tx['orgID'] == 'o1'
    assert item['price'] == Decimal('9.5')  # N attribute; a string 'S' would read back as '9.5'


def test_sync_import_stores_numeric_price(load, ddb):
    res = load('BulkImport').lambda_handler(
        {'httpMethod': 'POST', 'path': '/import', 'headers': HEADERS,
         'body': json.dumps({'rows': [{'name': 'Rice', 'quantity': 2, 'price': '3.25'}]})}, None)
    assert json.loads(res['body'])['inserted'] == 1
    item = ddb.Table('InventoryIQ').scan()['Items'][0]
    assert item['price'] == Decimal('3.25') and item['orgID'] == 'o1'


@pytest.mark.parametrize('job, member', [
    ({'userID': 'a@b.co', 'orgID': 'o1', 'status': 'pending'}, None),  # removed from the org
    ({'userID': 'a@b.co', 'orgID': 'o1', 'status': 'pending'}, 'viewer'),  # demoted below editor
    ({'userID': 'a@b.co', 'orgID': 'o1', 'status': 'completed'}, 'editor'),  # presigned URL reused
    ({'userID': 'x@y.co', 'orgID': 'o1', 'status': 'pending'}, 'editor'),  # job belongs to someone else
    (None, 'editor'),  # no job row
])
def test_async_import_rejects_stale_uploads(load, ddb, job, member):
    """SEC-2: the async path re-checks job owner, pending status and live editor membership before writing."""
    members = ddb.Table('OrgMembers')
    if member:
        members.put_item(Item={'orgID': 'o1', 'userID': 'a@b.co', 'role': member, 'status': 'active'})
    else:
        members.delete_item(Key={'orgID': 'o1', 'userID': 'a@b.co'})
    if job:
        ddb.Table('ImportJobs').put_item(Item={'jobId': 'j1', **job})
    s3 = boto3.client('s3')
    s3.create_bucket(Bucket='imports-test')
    s3.put_object(Bucket='imports-test', Key='uploads/a@b.co/j1.csv', Body=b'name,quantity\nRice,5\n')
    load('BulkImportAsync').lambda_handler(
        {'Records': [{'s3': {'bucket': {'name': 'imports-test'}, 'object': {'key': 'uploads/a@b.co/j1.csv'}}}]}, None)
    assert ddb.Table('InventoryIQ').scan()['Items'] == []
    assert ddb.Table('InventoryTransactions').scan()['Items'] == []


def test_async_import_decodes_url_encoded_s3_key(load, ddb):
    """S3 events URL-encode object keys ('@' -> '%40'); the owner check and GetObject need the decoded key."""
    ddb.Table('OrgMembers').put_item(Item={'orgID': 'o1', 'userID': 'owner@shop.test', 'role': 'owner', 'status': 'active'})
    ddb.Table('ImportJobs').put_item(Item={'jobId': 'j2', 'userID': 'owner@shop.test', 'orgID': 'o1', 'status': 'pending'})
    s3 = boto3.client('s3')
    s3.create_bucket(Bucket='imports-test')
    s3.put_object(Bucket='imports-test', Key='uploads/owner@shop.test/j2.csv', Body=b'name,quantity\nRice,5\n')
    res = load('BulkImportAsync').lambda_handler(
        {'Records': [{'s3': {'bucket': {'name': 'imports-test'}, 'object': {'key': 'uploads/owner%40shop.test/j2.csv'}}}]}, None)
    assert res['statusCode'] == 200
    assert [i['name'] for i in ddb.Table('InventoryIQ').scan()['Items']] == ['Rice']
