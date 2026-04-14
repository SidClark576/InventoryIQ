import json
import boto3
import os
import uuid
from datetime import datetime
from decimal import Decimal

# Initialize DynamoDB tables
# Main inventory table and transactions table for audit logging
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
tx_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

def lambda_handler(event, context):
    """
    Creates a new inventory item and logs the transaction.

    Flow:
    1. Parse request body and validate required fields (name)
    2. Generate unique itemID (UUID)
    3. Create item object with all fields (use defaults where not provided)
    4. Insert item into InventoryIQ table
    5. Create transaction log record with changeType='create'
    6. Return created item with 201 status

    Request Body Fields:
    - name: Required. Product name.
    - category: Optional, defaults to 'Uncategorized'
    - quantity: Optional, defaults to 0
    - price: Optional, defaults to 0 (stored as Decimal in DynamoDB)
    - lowStockThreshold: Optional, defaults to 10
    - description: Optional, defaults to ''
    - userID: User email for multi-tenant isolation

    Response: 201 with created item object
    """
    try:
        # Parse JSON body from API Gateway event
        body = json.loads(event.get('body', '{}'))

        # Validate required field: product name cannot be empty
        if not body.get('name'):
            return response(400, {'error': 'Product name is required'})

        # Generate unique ID and current timestamp
        item_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        user_id = body.get('userID', '').strip()

        # Build item object with all required fields
        # Price is stored as Decimal for precision; quantity and threshold as int
        item = {
            'itemID': item_id,
            'userID': user_id,
            'name': body.get('name'),
            'description': body.get('description', ''),
            'category': body.get('category', 'Uncategorized'),
            'quantity': int(body.get('quantity', 0)),
            'price': Decimal(str(body.get('price', 0))),  # Use Decimal for money
            'lowStockThreshold': int(body.get('lowStockThreshold', 10)),
            'createdAt': timestamp,
            'updatedAt': timestamp
        }

        # Write item to inventory table
        table.put_item(Item=item)
        # Convert price back to float for JSON response
        item['price'] = float(item['price'])

        # Write transaction log: records that item was created with initial quantity
        # This creates audit trail for inventory changes
        tx_table.put_item(Item={
            'transactionID': str(uuid.uuid4()),
            'itemID': item_id,
            'itemName': item['name'],
            'userID': user_id,
            'changeType': 'create',  # Type: create, stock_in, stock_out, update, delete
            'quantityBefore': 0,
            'quantityAfter': item['quantity'],
            'quantityDelta': item['quantity'],
            'notes': 'Item created',
            'createdAt': timestamp
        })

        return response(201, {'message': 'Item added successfully', 'item': item})

    except Exception as e:
        return response(500, {'error': str(e)})

def response(status_code, body):
    """
    Helper function to format Lambda response with consistent headers and CORS.

    Args:
        status_code: HTTP status code (201, 400, 500, etc.)
        body: Dictionary to be JSON-encoded in response body

    Returns: API Gateway Lambda Proxy Integration response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',  # Allow cross-origin requests
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
        },
        'body': json.dumps(body)
    }
