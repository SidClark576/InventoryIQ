import json
import uuid
import boto3
import os
from datetime import datetime

# Initialize DynamoDB tables for inventory and transaction logging
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
tx_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

def lambda_handler(event, context):
    """
    Deletes an inventory item and logs the transaction.

    Flow:
    1. Extract itemID from URL path
    2. Read existing item BEFORE deletion for audit trail
    3. Delete item from inventory table
    4. Create transaction record with changeType='delete'
       - quantityBefore = original quantity
       - quantityAfter = 0 (item removed from inventory)
       - quantityDelta = negative of original quantity
    5. Return success message

    Path Parameters:
    - itemID: ID of item to delete

    Response: 200 with success message

    Note: This is a hard delete. Item is removed completely from inventory.
    Transaction log preserves the data for audit purposes.
    """
    try:
        # Extract itemID from URL path parameters (set by API Gateway)
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        # Read existing item BEFORE deletion
        # This is critical for creating an accurate audit trail
        # We need to preserve the item name, userID, and quantity for the transaction log
        existing = table.get_item(Key={'itemID': item_id}).get('Item', {})

        # Delete item from inventory table
        table.delete_item(Key={'itemID': item_id})

        # Write transaction log entry with deletion details
        # This creates an audit trail showing:
        # - What item was deleted (name, ID)
        # - Who owned it (userID)
        # - How much quantity was lost (quantityDelta is negative)
        tx_table.put_item(Item={
            'transactionID': str(uuid.uuid4()),
            'itemID': item_id,
            'itemName': existing.get('name', ''),
            'userID': existing.get('userID', ''),
            'changeType': 'delete',  # Type: create, stock_in, stock_out, update, delete
            'quantityBefore': int(existing.get('quantity', 0)),  # Original quantity
            'quantityAfter': 0,  # Item completely removed
            'quantityDelta': -int(existing.get('quantity', 0)),  # Negative delta for deletion
            'notes': 'Item deleted',
            'createdAt': datetime.utcnow().isoformat()
        })

        return response(200, {'message': f'Item {item_id} deleted successfully'})

    except Exception as e:
        return response(500, {'error': str(e)})

def response(status_code, body):
    """
    Helper function to format Lambda response with consistent headers and CORS.

    Args:
        status_code: HTTP status code
        body: Dictionary to be JSON-encoded

    Returns: API Gateway Lambda Proxy Integration response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
        },
        'body': json.dumps(body)
    }
