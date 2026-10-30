"""AC2: expiry alerts go out once per state (soon, expired); a new expiresAt re-arms both."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

TODAY = date(2026, 11, 10)


@pytest.fixture
def alert(load, monkeypatch):
    monkeypatch.setenv('SNS_TOPIC_ARN', 'arn:aws:sns:us-east-1:123456789012:alerts')
    mod = load('DailyAlert')
    sent = []
    monkeypatch.setattr(mod.sns, 'publish', lambda **kw: sent.append(kw))

    def run(day=TODAY):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(day.year, day.month, day.day, 9, tzinfo=timezone.utc)
        monkeypatch.setattr(mod, 'datetime', Clock)
        sent.clear()
        body = json.loads(mod.lambda_handler({}, None)['body'])
        return body, sent[0]['Message']
    mod.run = run
    return mod


def _put(mod, item_id, expires, **extra):
    mod.table.put_item(Item={'itemID': item_id, 'name': item_id, 'quantity': 50, 'version': 1,
                             'expiresAt': expires, **extra})


def _day(days):
    return (TODAY + timedelta(days=days)).isoformat()


def test_once_per_state_and_rearm(alert):
    _put(alert, 'milk', _day(3))
    _put(alert, 'eggs', _day(-1))
    _put(alert, 'later', _day(30))
    _put(alert, 'undated', '')
    _put(alert, 'binned', _day(-2), deletedAt='2026-11-01T00:00:00+00:00')
    alert.table.put_item(Item={'itemID': 'old', 'name': 'old', 'quantity': 50, 'version': 1})

    body, msg = alert.run()
    assert (body['expired'], body['expiringSoon']) == (1, 1)
    assert 'milk' in msg and 'eggs' in msg and 'later' not in msg and 'binned' not in msg
    assert 'Expir' in body['subject']

    body, _ = alert.run()
    assert (body['expired'], body['expiringSoon']) == (0, 0)

    body, msg = alert.run(TODAY + timedelta(days=4))  # milk is now past its date
    assert (body['expired'], body['expiringSoon']) == (1, 0) and 'milk' in msg

    body, _ = alert.run(TODAY + timedelta(days=4))
    assert (body['expired'], body['expiringSoon']) == (0, 0)

    alert.table.update_item(Key={'itemID': 'milk'}, UpdateExpression='SET expiresAt = :e',
                            ExpressionAttributeValues={':e': _day(6)})
    body, msg = alert.run(TODAY + timedelta(days=4))
    assert (body['expired'], body['expiringSoon']) == (0, 1) and 'milk' in msg
    body, msg = alert.run(TODAY + timedelta(days=7))
    assert (body['expired'], body['expiringSoon']) == (1, 0) and 'milk' in msg

    assert alert.table.get_item(Key={'itemID': 'milk'})['Item']['version'] == 1


def test_today_and_day_seven_are_soon_day_eight_is_not(alert):
    _put(alert, 'today', _day(0))
    _put(alert, 'week', _day(7))
    _put(alert, 'eight', _day(8))
    body, _ = alert.run()
    assert (body['expired'], body['expiringSoon']) == (0, 2)
