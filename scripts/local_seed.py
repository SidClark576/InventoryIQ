#!/usr/bin/env python3
"""Seed the local backend (Floci): live table layouts, fake AWS resources, and a Panindo test store.

Run by scripts/dev_local.sh after Floci and scripts/local_api.py are up. Accounts are created through the
real /auth/register; the shared test password lives in .local/test-login.json (gitignored).
"""
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_api  # noqa: E402

LOGIN_FILE = local_api.ROOT / '.local' / 'test-login.json'
TABLES = Path(__file__).resolve().parent / 'local' / 'tables.json'
OWNER = 'owner@panindo.local'
STAFF = 'staff@panindo.local'
# Not live: ImportJobs is named in BulkImport*.py (IMPORT_JOBS_TABLE) but has no table in AWS.
IMPORT_JOBS = {'TableName': 'ImportJobs', 'KeySchema': [{'AttributeName': 'jobId', 'KeyType': 'HASH'}],
               'AttributeDefinitions': [{'AttributeName': 'jobId', 'AttributeType': 'S'}]}

# (name, category, price, quantity, lowStockThreshold): a sari-sari store; some low, three out of stock.
ITEMS = [
    ('Holiday Corned Beef 215g', 'Canned Goods', 53, 24, 10),
    ('Wow Ulam 150g', 'Canned Goods', 35, 6, 10),
    ('Argentina Corned Beef 150g', 'Canned Goods', 40, 18, 10),
    ('Youngstown Corned Beef 150g', 'Canned Goods', 32, 0, 8),
    ('Fiesta Beef Loaf 150g', 'Canned Goods', 28, 15, 8),
    ('555 Tuna Afritada 155g', 'Canned Goods', 30, 4, 8),
    ('Hunts Pork and Beans 230g', 'Canned Goods', 38, 12, 6),
    ('Argentina Meat Loaf 150g', 'Canned Goods', 27, 20, 8),
    ('Lucky Me Pancit Canton Original', 'Noodles', 16, 48, 20),
    ('Lucky Me Pancit Canton Chilimansi', 'Noodles', 16, 9, 20),
    ('Lucky Me Beef Mami', 'Noodles', 12, 30, 15),
    ('Lucky Me Chicken Mami', 'Noodles', 12, 0, 15),
    ('Payless Xtra Big Pancit Canton', 'Noodles', 18, 25, 10),
    ('Coca-Cola 290ml', 'Drinks', 20, 36, 12),
    ('Royal Tru-Orange 290ml', 'Drinks', 20, 10, 12),
    ('Sprite 290ml', 'Drinks', 20, 24, 12),
    ('C2 Green Tea Apple 230ml', 'Drinks', 18, 30, 12),
    ('Nescafe 3in1 Original Twin Pack', 'Drinks', 14, 60, 24),
    ('Milo Sachet 22g', 'Drinks', 10, 0, 24),
    ('Safeguard Bar Soap 60g', 'Toiletries', 25, 14, 6),
    ('Palmolive Shampoo Sachet 12ml', 'Toiletries', 8, 72, 24),
    ('Colgate Toothpaste 25ml', 'Toiletries', 30, 3, 6),
    ('Joy Dishwashing Liquid 40ml', 'Toiletries', 15, 20, 8),
    ('Surf Powder Detergent 65g', 'Toiletries', 12, 40, 12),
    ('Tide Bar 125g', 'Toiletries', 22, 5, 8),
]


def barcode(i):
    return f'4800{i:08d}0'


def _password():
    if LOGIN_FILE.exists():
        return json.loads(LOGIN_FILE.read_text())['password']
    return secrets.token_urlsafe(9) + 'Aa1'  # meets Authentication.mjs PASSWORD_REGEX


def create_aws(session):
    ddb = session.client('dynamodb')
    for t in json.loads(TABLES.read_text())['tables'] + [IMPORT_JOBS]:
        spec = {k: v for k, v in t.items() if v or k != 'GlobalSecondaryIndexes'}
        ddb.create_table(BillingMode='PAY_PER_REQUEST', **spec)
    env = local_api.AWS_ENV
    session.client('s3').create_bucket(Bucket=env['IMPORT_BUCKET'])
    session.client('sns').create_topic(Name=env['SNS_TOPIC_ARN'].rsplit(':', 1)[1])
    queue_url = session.client('sqs').create_queue(QueueName=env['SQS_QUEUE_URL'].rsplit('/', 1)[1])['QueueUrl']
    if queue_url != env['SQS_QUEUE_URL']:
        raise SystemExit(f"SQS queue URL {queue_url} != runner's SQS_QUEUE_URL {env['SQS_QUEUE_URL']}")
    session.client('ses').verify_email_identity(EmailAddress=env['SES_SENDER'])
    session.client('secretsmanager').create_secret(Name=env['API_KEY_SECRET'], SecretString=secrets.token_urlsafe(24))


def register(email, password):
    url = f'http://localhost:{local_api.PORT}/auth/register'
    data = json.dumps({'email': email, 'password': password}).encode()
    for _ in range(60):  # the runner may still be starting
        try:
            req = urllib.request.Request(url, data=data, method='POST', headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30):
                return
        except urllib.error.URLError as e:
            if isinstance(e, urllib.error.HTTPError):
                raise SystemExit(f'register {email} failed: {e.code} {e.read().decode()}')
            time.sleep(0.5)
    raise SystemExit('local API runner did not start')


def seed_store(db, org_id):
    now = datetime.now(timezone.utc)
    items, cache, txs = db.Table('InventoryIQ'), db.Table('BarcodeCache'), db.Table('InventoryTransactions')
    for i, (name, category, price, qty, low) in enumerate(ITEMS, 1):
        created = (now - timedelta(days=30 - i)).isoformat()
        item_id = str(uuid.uuid4())
        items.put_item(Item={
            'itemID': item_id, 'userID': OWNER, 'orgID': org_id, 'name': name, 'description': '',
            'category': category, 'supplierID': '', 'quantity': qty, 'price': Decimal(price),
            'lowStockThreshold': low, 'barcode': barcode(i), 'version': 1, 'createdAt': created, 'updatedAt': created,
        })
        cache.put_item(Item={'code': barcode(i), 'name': name, 'category': category, 'brand': name.split()[0],
                             'imageUrl': '', 'ttl': int(now.timestamp()) + 10 * 365 * 86400})
        if i % 3 == 1:  # 9 transactions: a create, and a sale for the odd ones
            sold = 2 if i % 2 else 0
            txs.put_item(Item={
                'transactionID': str(uuid.uuid4()), 'itemID': item_id, 'itemName': name, 'userID': OWNER,
                'orgID': org_id, 'changeType': 'stock_out' if sold else 'create', 'quantityBefore': qty + sold,
                'quantityAfter': qty, 'quantityDelta': -sold if sold else qty,
                'notes': 'Sold' if sold else 'Item created', 'createdAt': (now - timedelta(hours=i)).isoformat(),
            })


def main():
    os.environ.update(local_api.AWS_ENV)  # endpoint -> Floci and fake keys, before any client is built
    import boto3
    session = boto3.Session()
    create_aws(session)
    password = _password()
    register(OWNER, password)
    register(STAFF, password)
    db = session.resource('dynamodb')
    members = db.Table('OrgMembers')
    org_id = members.query(IndexName='userID-index', KeyConditionExpression='userID = :u',
                           ExpressionAttributeValues={':u': OWNER})['Items'][0]['orgID']
    db.Table('Organizations').update_item(Key={'orgID': org_id}, UpdateExpression='SET #n = :n, memberCount = :c',
                                          ExpressionAttributeNames={'#n': 'name'},
                                          ExpressionAttributeValues={':n': 'Tindahan ni Aling Nena', ':c': 2})
    members.put_item(Item={'orgID': org_id, 'userID': STAFF, 'role': 'editor', 'status': 'active',
                           'joinedAt': datetime.now(timezone.utc).isoformat()})
    seed_store(db, org_id)
    LOGIN_FILE.parent.mkdir(exist_ok=True)
    LOGIN_FILE.write_text(json.dumps({'owner': OWNER, 'staff': STAFF, 'password': password}, indent=2) + '\n')
    print(f'Seeded {len(ITEMS)} items in org {org_id}; test login in {LOGIN_FILE.relative_to(local_api.ROOT)}',
          flush=True)


if __name__ == '__main__':
    main()
