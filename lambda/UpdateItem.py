import json
import uuid
import boto3
import os
from datetime import datetime
from decimal import Decimal

# Initialize DynamoDB tables at module level so they are reused across warm Lambda invocations
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
tx_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

def lambda_handler(event, context):
    """
    Updates an existing inventory item and logs the transaction.

    Flow:
    1. Extract verified userID from X-Verified-UserID header (injected by Proxy.py)
    2. Extract itemID from URL path
    3. Read existing item and verify ownership
    4. Validate request body fields and build dynamic UpdateExpression
    5. Execute update and get returned item
    6. Determine transaction type based on quantity change:
       - stock_in: quantity increased
       - stock_out: quantity decreased
       - update: other fields changed or quantity same
    7. Log transaction with before/after quantities and delta
    8. Return updated item

    Auth: X-Verified-UserID header (verified by Proxy.py after JWT validation)
    Path Parameters:
    - itemID: ID of item to update

    Request Body (all optional):
    - quantity: New quantity (non-negative integer)
    - name: Product name (uses 'name' alias #nm because 'name' is reserved)
    - price: Unit price (non-negative number)
    - category: Category name
    - description: Item description
    - lowStockThreshold: Reorder threshold (positive integer)
    - notes: Transaction notes

    Response: 200 with updated item object, 401 if auth header missing, 403 if not owner
    """
    try:
        # Extract verified userID from header (injected by Proxy.py after JWT validation)
        user_id = event.get('headers', {}).get('x-verified-userid', '').strip()
        if not user_id:
            return response(401, {'error': 'Missing or invalid authorization'})

        # Extract itemID from URL path parameters (set by API Gateway)
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        # Parse request body
        body = json.loads(event.get('body', '{}'))
        timestamp = datetime.utcnow().isoformat()

        # Read existing item BEFORE update to capture quantityBefore for transaction log
        # This is critical for accurate audit trail
        result = table.get_item(Key={'itemID': item_id})
        existing = result.get('Item')

        # Return 404 if item does not exist (prevents information leakage)
        if not existing:
            return response(404, {'error': 'Item not found'})

        # Ownership verification: ensure user can only modify their own items
        # Use verified userID from header, not from request body
        if existing.get('userID') != user_id:
            return response(403, {'error': 'Forbidden'})

        # Validate fields before building UpdateExpression
        if 'quantity' in body:
            try:
                qty = int(body['quantity'])
                if qty < 0:
                    return response(400, {'error': 'Quantity cannot be negative'})
            except (ValueError, TypeError):
                return response(400, {'error': 'Quantity must be a non-negative integer'})

        if 'name' in body:
            name = body['name']
            if not name or not str(name).strip():
                return response(400, {'error': 'Product name cannot be empty'})
            if len(str(name)) > 200:
                return response(400, {'error': 'Product name must be 200 characters or less'})

        if 'price' in body:
            try:
                price = Decimal(str(body['price']))
                if price < 0:
                    return response(400, {'error': 'Price cannot be negative'})
            except (ValueError, TypeError):
                return response(400, {'error': 'Price must be a valid number'})

        if 'lowStockThreshold' in body:
            try:
                lst = int(body['lowStockThreshold'])
                if lst <= 0:
                    return response(400, {'error': 'Low stock threshold must be a positive integer'})
            except (ValueError, TypeError):
                return response(400, {'error': 'Low stock threshold must be a positive integer'})

        # Build dynamic UpdateExpression - only include fields that are in the request
        update_expr = "SET updatedAt = :ts"
        expr_values = {':ts': timestamp}
        expr_names = {}

        # Conditionally add each field if present in request body
        if 'quantity' in body:
            update_expr += ", quantity = :qty"
            expr_values[':qty'] = int(body['quantity'])
        if 'name' in body:
            # Use expression alias #nm because 'name' is a reserved word in DynamoDB
            update_expr += ", #nm = :name"
            expr_values[':name'] = str(body['name']).strip()
            expr_names['#nm'] = 'name'
        if 'price' in body:
            update_expr += ", price = :price"
            expr_values[':price'] = Decimal(str(body['price']))  # Store as Decimal for precision
        if 'category' in body:
            update_expr += ", category = :cat"
            expr_values[':cat'] = str(body['category']).strip()
        if 'description' in body:
            update_expr += ", description = :desc"
            expr_values[':desc'] = str(body['description']).strip()
        if 'lowStockThreshold' in body:
            update_expr += ", lowStockThreshold = :lst"
            expr_values[':lst'] = int(body['lowStockThreshold'])

        # Prepare update_item kwargs - only include ExpressionAttributeNames if using reserved words
        update_kwargs = {
            'Key': {'itemID': item_id},
            'UpdateExpression': update_expr,
            'ExpressionAttributeValues': expr_values,
            'ReturnValues': 'ALL_NEW'  # Return the updated item
        }
        if expr_names:
            update_kwargs['ExpressionAttributeNames'] = expr_names

        # Execute update and get the updated item
        result = table.update_item(**update_kwargs)

        # Convert Decimal types to float for JSON response
        updated = result.get('Attributes', {})
        updated = {k: float(v) if isinstance(v, Decimal) else v for k, v in updated.items()}

        # Determine transaction type based on quantity change
        qty_before = int(existing.get('quantity', 0))
        qty_after = int(body['quantity']) if 'quantity' in body else qty_before

        # Classify the change:
        # - stock_in: restocking (quantity increased)
        # - stock_out: depletion (quantity decreased)
        # - update: other fields changed or quantity unchanged
        if qty_after > qty_before:
            change_type = 'stock_in'
        elif qty_after < qty_before:
            change_type = 'stock_out'
        else:
            change_type = 'update'

        # Write transaction log for audit trail
        tx_table.put_item(Item={
            'transactionID': str(uuid.uuid4()),
            'itemID': item_id,
            'itemName': body.get('name', existing.get('name', '')),
            'userID': user_id,  # Use verified userID from header
            'changeType': change_type,
            'quantityBefore': qty_before,
            'quantityAfter': qty_after,
            'quantityDelta': qty_after - qty_before,  # Positive = stock_in, Negative = stock_out
            'notes': body.get('notes', ''),
            'createdAt': timestamp
        })

        return response(200, {'message': 'Item updated', 'item': updated})

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
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key,Authorization',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
        },
        'body': json.dumps(body)
    }
