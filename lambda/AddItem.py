import json
import boto3
import os
import uuid
import re
from datetime import datetime
from decimal import Decimal

# Initialize DynamoDB tables
# Main inventory table and transactions table for audit logging
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
tx_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

def lambda_handler(event, context):
    """
    Creates a new inventory item and logs the transaction.

    Flow:
    1. Extract verified userID from X-Verified-UserID header (injected by Proxy.py)
    2. Parse request body and validate all fields
    3. Generate unique itemID (UUID)
    4. Create item object with all fields (use defaults where not provided)
    5. Insert item into InventoryIQ table
    6. Create transaction log record with changeType='create'
    7. Return created item with 201 status

    Request Body Fields:
    - name: Required. Product name (string, max 200 chars)
    - category: Optional, defaults to 'Uncategorized'
    - quantity: Optional, defaults to 0 (must be non-negative integer)
    - price: Optional, defaults to 0 (stored as Decimal; must be non-negative)
    - lowStockThreshold: Optional, defaults to 10 (must be positive integer)
    - description: Optional, defaults to ''

    Auth: X-Verified-UserID header (verified by Proxy.py after JWT validation)
    Response: 201 with created item object, 400 on validation error, 401 if auth header missing
    """
    try:
        # Extract verified userID from header (injected by Proxy.py after JWT validation)
        # API Gateway lowercases header names, so check for 'x-verified-userid'
        user_id = event.get('headers', {}).get('x-verified-userid', '').strip()
        if not user_id:
            return response(401, {'error': 'Missing or invalid authorization'})

        # Parse JSON body from API Gateway event
        body = json.loads(event.get('body', '{}'))

        # Validate required field: product name
        name = body.get('name', '').strip()
        if not name:
            return response(400, {'error': 'Product name is required'})
        if len(name) > 200:
            return response(400, {'error': 'Product name must be 200 characters or less'})

        # Validate optional numeric fields
        try:
            quantity = int(body.get('quantity', 0))
            if quantity < 0:
                return response(400, {'error': 'Quantity cannot be negative'})
        except (ValueError, TypeError):
            return response(400, {'error': 'Quantity must be a non-negative integer'})

        try:
            price = Decimal(str(body.get('price', 0)))
            if price < 0:
                return response(400, {'error': 'Price cannot be negative'})
        except (ValueError, TypeError):
            return response(400, {'error': 'Price must be a valid number'})

        try:
            low_stock_threshold = int(body.get('lowStockThreshold', 10))
            if low_stock_threshold <= 0:
                return response(400, {'error': 'Low stock threshold must be a positive integer'})
        except (ValueError, TypeError):
            return response(400, {'error': 'Low stock threshold must be a positive integer'})

        # Generate unique ID and current timestamp
        item_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Build item object with all required fields
        # Price is stored as Decimal for precision; quantity and threshold as int
        item = {
            'itemID': item_id,
            'userID': user_id,
            'name': name,
            'description': body.get('description', '').strip(),
            'category': body.get('category', 'Uncategorized').strip(),
            'quantity': quantity,
            'price': price,  # Already validated and converted to Decimal
            'lowStockThreshold': low_stock_threshold,
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
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key,Authorization',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
        },
        'body': json.dumps(body)
    }
