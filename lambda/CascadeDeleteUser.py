import json
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
import _logging

FUNCTION_NAME = 'CascadeDeleteUser'

dynamodb = boto3.resource('dynamodb')


def _log(email, step, count=None):
    """Never log the raw email (PII): hashed user ID only."""
    _logging.log_json(function=FUNCTION_NAME, userID_hash=_logging.hash_user(email), step=step, count=count)


def lambda_handler(event, context):
    try:
        # Tables
        inventory_table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
        transactions_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))
        sessions_table = dynamodb.Table(os.environ.get('SESSIONS_TABLE', 'Sessions'))
        auth_attempts_table = dynamodb.Table(os.environ.get('AUTH_ATTEMPTS_TABLE', 'AuthAttempts'))
        password_resets_table = dynamodb.Table(os.environ.get('PASSWORD_RESETS_TABLE', 'PasswordResets'))
        
        for record in event.get('Records', []):
            if record['eventName'] == 'REMOVE':
                old_image = record.get('dynamodb', {}).get('OldImage', {})
                # Get the email of the deleted user
                email = old_image.get('Email', {}).get('S')
                if not email:
                    continue
                
                _log(email, 'start')
                
                # 1. Delete all items from InventoryIQ for this user
                # Using the userID-index
                try:
                    res = inventory_table.query(
                        IndexName='userID-index',
                        KeyConditionExpression=Key('userID').eq(email)
                    )
                    items = res.get('Items', [])
                    while 'LastEvaluatedKey' in res:
                        res = inventory_table.query(
                            IndexName='userID-index',
                            KeyConditionExpression=Key('userID').eq(email),
                            ExclusiveStartKey=res['LastEvaluatedKey']
                        )
                        items.extend(res.get('Items', []))
                    
                    with inventory_table.batch_writer() as batch:
                        for item in items:
                            batch.delete_item(Key={'itemID': item['itemID']})
                    _log(email, 'items', len(items))
                except Exception as e:
                    _logging.capture_error(e, event=event, step='items')

                # 2. Delete all transactions for this user
                # No GSI, requires scan
                try:
                    res = transactions_table.scan(FilterExpression=Attr('userID').eq(email))
                    txs = res.get('Items', [])
                    while 'LastEvaluatedKey' in res:
                        res = transactions_table.scan(
                            FilterExpression=Attr('userID').eq(email),
                            ExclusiveStartKey=res['LastEvaluatedKey']
                        )
                        txs.extend(res.get('Items', []))
                    
                    with transactions_table.batch_writer() as batch:
                        for tx in txs:
                            batch.delete_item(Key={'transactionID': tx['transactionID']})
                    _log(email, 'transactions', len(txs))
                except Exception as e:
                    _logging.capture_error(e, event=event, step='transactions')
                
                # 3. Delete sessions
                try:
                    res = sessions_table.query(
                        IndexName='userID-index',
                        KeyConditionExpression=Key('userID').eq(email)
                    )
                    sessions = res.get('Items', [])
                    while 'LastEvaluatedKey' in res:
                        res = sessions_table.query(
                            IndexName='userID-index',
                            KeyConditionExpression=Key('userID').eq(email),
                            ExclusiveStartKey=res['LastEvaluatedKey']
                        )
                        sessions.extend(res.get('Items', []))
                    
                    with sessions_table.batch_writer() as batch:
                        for session in sessions:
                            batch.delete_item(Key={'sessionToken': session['sessionToken']})
                    _log(email, 'sessions', len(sessions))
                except Exception as e:
                    _logging.capture_error(e, event=event, step='sessions')
                
                # 4. Delete auth attempts
                try:
                    auth_attempts_table.delete_item(Key={'email': email.lower()})
                    _log(email, 'auth_attempts', 1)
                except Exception as e:
                    _logging.capture_error(e, event=event, step='auth_attempts')
                    
                # 5. Delete Password Resets (scan)
                try:
                    res = password_resets_table.scan(FilterExpression=Attr('userID').eq(email))
                    resets = res.get('Items', [])
                    while 'LastEvaluatedKey' in res:
                        res = password_resets_table.scan(
                            FilterExpression=Attr('userID').eq(email),
                            ExclusiveStartKey=res['LastEvaluatedKey']
                        )
                        resets.extend(res.get('Items', []))
                        
                    with password_resets_table.batch_writer() as batch:
                        for r in resets:
                            batch.delete_item(Key={'resetToken': r['resetToken']})
                    _log(email, 'password_resets', len(resets))
                except Exception as e:
                    _logging.capture_error(e, event=event, step='password_resets')

        return {'statusCode': 200, 'body': 'Cascade delete completed successfully'}
    except Exception as e:
        return _logging.server_error(e, event)
