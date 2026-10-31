"""Backend route table, shared by Proxy.py (PROXY_MODE=invoke) and scripts/local_api.py.

Module name == Lambda function name (scripts/deploy_lambdas.sh deploys each file under its own name).
"""
import urllib.parse

# (method, API Gateway resource, handler module): the routes frontend/src/api.ts calls.
ROUTES = [
    ('GET', '/items', 'GetAllItems'),
    ('POST', '/items', 'AddItem'),
    ('POST', '/items/import', 'BulkImport'),
    ('PUT', '/items/{itemID}', 'UpdateItem'),
    ('DELETE', '/items/{itemID}', 'DeleteItem'),
    ('POST', '/items/{itemID}/restore', 'RestoreItem'),
    ('GET', '/import/presign', 'BulkImport'),
    ('GET', '/import/{jobId}', 'BulkImport'),
    ('GET', '/insights', 'LowItemInsight'),
    ('GET', '/transactions', 'GetTransactions'),
    ('GET', '/categories', 'GetCategories'),
    ('DELETE', '/categories/{categoryName}', 'DeleteCategory'),
    ('GET', '/barcode/{code}', 'BarcodeLookup'),
    ('GET', '/orgs', 'Orgs'),
    ('POST', '/orgs/{id}/switch', 'Orgs'),
    ('PUT', '/orgs/{id}', 'Orgs'),
    ('GET', '/orgs/{id}/members', 'OrgMembers'),
    ('POST', '/orgs/{id}/invites', 'OrgInvites'),
    ('POST', '/org-invites/{token}/accept', 'OrgInvites'),
]


def match_route(method, path, routes):
    """Return (module, resource, decoded pathParameters or None) for a backend path, or None."""
    parts = path.strip('/').split('/')
    for route_method, resource, module in routes:
        segs = resource.strip('/').split('/')
        if route_method != method or len(segs) != len(parts):
            continue
        params = {}
        for seg, part in zip(segs, parts):
            if seg.startswith('{'):
                params[seg[1:-1]] = urllib.parse.unquote(part)
            elif seg != part:
                break
        else:
            return module, resource, params or None
    return None
