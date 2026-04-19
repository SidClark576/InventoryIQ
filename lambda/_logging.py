import json
import time
import hashlib
import os

FUNCTION_NAME = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown')


def log_json(event=None, level='INFO', function=None, latency_ms=None,
             userID_hash=None, is_error=False, extra_metric=None,
             count_request=True, **kwargs):
    """
    Emit a structured log line in CloudWatch Embedded Metric Format (EMF).
    CloudWatch auto-extracts metrics from the _aws envelope.

    Metrics emitted:
      iq.requests   (Count)    — every call (skip with count_request=False)
      iq.errors     (Count)    — only when is_error=True
      iq.latency_ms (Milliseconds) — only when latency_ms provided

    Dimensions: {function}
    Namespace:  InventoryIQ
    """
    fn = function or FUNCTION_NAME
    now_ms = int(time.time() * 1000)

    metrics = ([{"Name": "iq.requests", "Unit": "Count"}] if count_request else [])
    if is_error:
        metrics.append({"Name": "iq.errors", "Unit": "Count"})
    if latency_ms is not None:
        metrics.append({"Name": "iq.latency_ms", "Unit": "Milliseconds"})
    if extra_metric is not None:
        # extra_metric: (name, unit) or (name, unit, value); value defaults to 1
        em_name = extra_metric[0]
        em_unit = extra_metric[1]
        em_val  = extra_metric[2] if len(extra_metric) > 2 else 1
        metrics.append({"Name": em_name, "Unit": em_unit})

    record = {
        "_aws": {
            "Timestamp": now_ms,
            "CloudWatchMetrics": [{
                "Namespace": "InventoryIQ",
                "Dimensions": [["function"]],
                "Metrics": metrics
            }]
        },
        "level": level,
        "function": fn,
        **({"iq.requests": 1} if count_request else {}),
        "iq.errors": 1 if is_error else 0,
    }

    if latency_ms is not None:
        record["iq.latency_ms"] = round(latency_ms, 2)
    if extra_metric is not None:
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
