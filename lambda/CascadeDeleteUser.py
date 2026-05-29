import json
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
import _logging

FUNCTION_NAME = 'CascadeDeleteUser'

dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    try:
        # Tables
        inventory_table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
        transactions_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))
        sessions_table = dynamodb.Table(os.environ.get('SESSIONS_TABLE', 'Sessions'))
        auth_attempts_table = dynamodb.Table(os.environ.get('AUTH_ATTEMPTS_TABLE', 'AuthAttempts'))
        password_resets_table = dynamodb.Table(os.environ.get('PASSWORD_RESETS_TABLE', 'PasswordResets'))
        suppliers_table = dynamodb.Table(os.environ.get('SUPPLIERS_TABLE', 'Suppliers'))
        
        for record in event.get('Records', []):
            if record['eventName'] == 'REMOVE':
                old_image = record.get('dynamodb', {}).get('OldImage', {})
                # Get the email of the deleted user
                email = old_image.get('Email', {}).get('S')
                if not email:
                    continue
                
                print(f"User {email} was deleted. Starting cascade delete.")
                
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
                    print(f"Deleted {len(items)} items from InventoryIQ for {email}")
                except Exception as e:
                    print(f"Error deleting items from InventoryIQ: {str(e)}")

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
                    print(f"Deleted {len(txs)} transactions from InventoryTransactions for {email}")
                except Exception as e:
                    print(f"Error deleting transactions: {str(e)}")
                
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
                    print(f"Deleted {len(sessions)} sessions for {email}")
                except Exception as e:
                    print(f"Error deleting sessions: {str(e)}")
                
                # 4. Delete auth attempts
                try:
                    auth_attempts_table.delete_item(Key={'email': email.lower()})
                    print(f"Deleted AuthAttempt record for {email}")
                except Exception as e:
                    print(f"Error deleting auth attempts: {str(e)}")
                    
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
                    print(f"Deleted {len(resets)} password resets for {email}")
                except Exception as e:
                    print(f"Error deleting password resets: {str(e)}")

                # 6. Delete Suppliers
                try:
                    res = suppliers_table.query(
                        IndexName='userID-index',
                        KeyConditionExpression=Key('userID').eq(email)
                    )
                    suppliers = res.get('Items', [])
                    while 'LastEvaluatedKey' in res:
                        res = suppliers_table.query(
                            IndexName='userID-index',
                            KeyConditionExpression=Key('userID').eq(email),
                            ExclusiveStartKey=res['LastEvaluatedKey']
                        )
                        suppliers.extend(res.get('Items', []))
                        
                    with suppliers_table.batch_writer() as batch:
                        for s in suppliers:
                            batch.delete_item(Key={'supplierID': s['supplierID']})
                    print(f"Deleted {len(suppliers)} suppliers for {email}")
                except Exception as e:
                    print(f"Error deleting suppliers: {str(e)}")
                    
        return {'statusCode': 200, 'body': 'Cascade delete completed successfully'}
    except Exception as e:
        print(f"Critical Error in CascadeDeleteUser: {str(e)}")
        return {'statusCode': 500, 'body': 'Internal Server Error'}
