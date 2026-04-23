import json
import boto3
import os
import urllib.request
import urllib.error
from decimal import Decimal
from datetime import datetime, timezone
import time as _time
import _logging

FUNCTION_NAME = 'BarcodeLookup'

CACHE_TABLE = os.environ.get('BARCODE_CACHE_TABLE', 'BarcodeCache')
UPCITEMDB_API_KEY = os.environ.get('UPCITEMDB_API_KEY', '')

CACHE_TTL_DAYS = 30

dynamodb = boto3.resource('dynamodb')
cache_table = dynamodb.Table(CACHE_TABLE)


def _headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
        'Access-Control-Allow-Methods': 'OPTIONS,GET',
    }


def _ok(body):
    return {'statusCode': 200, 'headers': _headers(), 'body': json.dumps(body)}


def _err(status, msg):
    return {'statusCode': status, 'headers': _headers(), 'body': json.dumps({'error': msg})}


def _lookup_off(code):
    """Call Open Food Facts API. Returns normalized dict or None."""
    try:
        url = f'https://world.openfoodfacts.org/api/v0/product/{code}.json'
        req = urllib.request.Request(url, headers={'User-Agent': 'InventoryIQ/1.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        if data.get('status') != 1:
            return None
        p = data.get('product', {})
        name = (
            p.get('product_name_en') or
            p.get('product_name') or
            p.get('abbreviated_product_name') or
            ''
        ).strip()
        if not name:
            return None
        categories_raw = p.get('categories_tags', [])
        category = 'Uncategorized'
        if categories_raw:
            last = categories_raw[-1]
            if ':' in last:
                last = last.split(':', 1)[1]
            category = last.replace('-', ' ').title()
        return {
            'name': name,
            'category': category,
            'brand': p.get('brands', '').strip(),
            'imageUrl': p.get('image_front_url', ''),
            'source': 'openfoodfacts',
        }
    except Exception:
        return None


def _lookup_upc(code):
    """Call UPC Item DB API. Returns normalized dict or None."""
    try:
        url = f'https://api.upcitemdb.com/prod/trial/lookup?upc={code}'
        req_headers = {'User-Agent': 'InventoryIQ/1.0', 'Accept': 'application/json'}
        if UPCITEMDB_API_KEY:
            req_headers['user_key'] = UPCITEMDB_API_KEY
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        items = data.get('items', [])
        if not items:
            return None
        p = items[0]
        name = (p.get('title') or '').strip()
        if not name:
            return None
        category = (p.get('category') or 'Uncategorized').strip()
        images = p.get('images', [])
        return {
            'name': name,
            'category': category,
            'brand': (p.get('brand') or '').strip(),
            'imageUrl': images[0] if images else '',
            'source': 'upcitemdb',
        }
    except Exception:
        return None


def lambda_handler(event, context):
    t0 = _time.time()
    res = _handle(event, context)
    _logging.log_json(
        event=event,
        function=FUNCTION_NAME,
        latency_ms=(_time.time() - t0) * 1000,
        status=res.get('statusCode'),
        is_error=res.get('statusCode', 200) >= 500,
    )
    return res


def _handle(event, context):
    """
    Lookup product metadata by barcode (EAN/UPC/Code128).

    Flow:
    1. Extract code from pathParameters
    2. Check BarcodeCache DynamoDB table (30-day TTL)
    3. On miss: query Open Food Facts, then UPC Item DB
    4. Store result in cache with TTL = now + 30 days
    5. Return {name, category, brand, imageUrl, source}

    Returns 404 if no product found in any source.
    """
    try:
        path_params = event.get('pathParameters') or {}
        code = (path_params.get('code') or '').strip()

        if not code:
            return _err(400, 'barcode code is required in path')

        # Reject obviously invalid barcodes (all same digit, non-numeric, wrong length)
        if not code.isdigit() or not (8 <= len(code) <= 14) or len(set(code)) < 2:
            return _err(404, f'No product found for barcode {code}')

        # Check cache first
        cache_resp = cache_table.get_item(Key={'code': code})
        cached = cache_resp.get('Item')
        if cached:
            result = {k: (float(v) if isinstance(v, Decimal) else v)
                      for k, v in cached.items()
                      if k not in ('code', 'ttl')}
            result['source'] = 'cache'
            return _ok(result)

        # External lookup: Open Food Facts → UPC Item DB
        product = _lookup_off(code) or _lookup_upc(code)

        if not product:
            return _err(404, f'No product found for barcode {code}')

        # Write to cache (TTL = 30 days from now)
        ttl = int(datetime.now(timezone.utc).timestamp()) + (CACHE_TTL_DAYS * 86400)
        cache_table.put_item(Item={
            'code': code,
            'name': product['name'],
            'category': product['category'],
            'brand': product.get('brand', ''),
            'imageUrl': product.get('imageUrl', ''),
            'ttl': ttl,
        })

        return _ok(product)

    except Exception as e:
        return _err(500, str(e))
