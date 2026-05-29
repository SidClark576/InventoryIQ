import json
import time
import hashlib
import os
import sys

# Add python_vendor to path for sentry-sdk
sys.path.append(os.path.join(os.path.dirname(__file__), 'python_vendor'))

try:
    import sentry_sdk
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
    sentry_sdk.init(
        dsn="https://cc83f9a25ccfc1b1228ac3a5b12958b8@o4511472709926912.ingest.us.sentry.io/4511472719233024",
        integrations=[AwsLambdaIntegration()],
        traces_sample_rate=1.0,
    )
except ImportError:
    pass

FUNCTION_NAME = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown')


def log_json(event=None, level='INFO', function=None, latency_ms=None,
             userID_hash=None, is_error=False, extra_metric=None,
             count_request=True, **kwargs):
    """
    Emit a structured log line without CloudWatch Embedded Metric Format (EMF)
    to save costs. Sentry integration can be added here later.
    """
    fn = function or FUNCTION_NAME

    record = {
        "level": level,
        "function": fn,
        "is_error": is_error,
    }

    if latency_ms is not None:
        record["latency_ms"] = round(latency_ms, 2)
    if extra_metric is not None:
        em_name = extra_metric[0]
        em_val  = extra_metric[2] if len(extra_metric) > 2 else 1
        record[em_name] = em_val
    if userID_hash is not None:
        record["userID_hash"] = userID_hash

    # Extract request context from event
    if event:
        record["httpMethod"] = event.get("httpMethod", "")
        path_params = event.get("pathParameters") or {}
        record["path"] = path_params.get("proxy", event.get("resource", ""))
        req_ctx = event.get("requestContext") or {}
        record["requestId"] = req_ctx.get("requestId", "")

    record.update(kwargs)
    print(json.dumps(record))


def hash_user(user_id):
    """Return first 12 hex chars of sha256(user_id). Returns None if falsy."""
    if not user_id:
        return None
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]
