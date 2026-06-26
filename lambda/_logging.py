import json
import time
import hashlib
import os
import sys

# Add python_vendor to path for sentry-sdk
sys.path.append(os.path.join(os.path.dirname(__file__), 'python_vendor'))

try:
    import sentry_sdk  # type: ignore[import-not-found]  # vendored in python_vendor/ (see sys.path above)
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration  # type: ignore[import-not-found]
    _dsn = os.environ.get('SENTRY_DSN')
    if _dsn:
        sentry_sdk.init(
            dsn=_dsn,
            integrations=[AwsLambdaIntegration()],
            traces_sample_rate=1.0,
        )
except ImportError:
    sentry_sdk = None

FUNCTION_NAME = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown')

# ponytail: stdout off by default to keep CloudWatch ingestion ~$0; errors go to Sentry.
# Set LOG_STDOUT=1 to re-enable structured stdout logs (e.g. local debugging).
_LOG_STDOUT = os.environ.get('LOG_STDOUT', '').lower() in ('1', 'true', 'yes')


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
    if _LOG_STDOUT:
        print(json.dumps(record))


def capture_error(exc=None, **context):
    """Send an error to Sentry. Pass the caught exception for a full stack
    trace, plus optional context (userID_hash, requestId, etc.). No-op if
    sentry_sdk is unavailable or SENTRY_DSN is unset."""
    if sentry_sdk is None:
        return
    with sentry_sdk.push_scope() as scope:
        for key, value in context.items():
            scope.set_tag(key, value)
        if exc is not None:
            sentry_sdk.capture_exception(exc)
        else:
            sentry_sdk.capture_message(context.get('message', 'error'), level='error')


def hash_user(user_id):
    """Return first 12 hex chars of sha256(user_id). Returns None if falsy."""
    if not user_id:
        return None
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]
