---
title: "InventoryIQ-Alerts SNS topic has no confirmed subscribers, so DailyAlert emails/SMS reach nobody"
author: Sidney
date: 2026-10-30
branch: feat/item-expiry-alerts
cost: { minutes: 19, tokens: 264175 }
id: l-93f91727
scope: repo
status: active
src: agent
---

## Decided
Job 015 live check (2026-10-30): DailyAlert publishes fine and the expiry once-per-state logic works in prod, but the topic InventoryIQ-Alerts (the only SNS topic, SNS_TOPIC_ARN on DailyAlert) has 0 confirmed subscriptions and 69 pending ones that were never confirmed. No daily report, low-stock or expiry alert has been reaching anyone.

## Tried and ruled out
- Treating a 200 "Daily alert sent." from DailyAlert as proof of delivery: SNS accepts the publish even with no confirmed subscribers.

## Watch out
- Before saying alerts work, check GetTopicAttributes SubscriptionsConfirmed > 0. An email subscription needs the recipient to click the confirm link; SMS needs an SNS origination identity in this account.
- InventoryIQ-LambdaExecutionRole is shared by every Lambda and has broad managed policies (DynamoDBFullAccess, SNS/SQS/SES full access, SecretsManagerReadWrite), so IAM never blocks a new write, and it is over-privileged.
