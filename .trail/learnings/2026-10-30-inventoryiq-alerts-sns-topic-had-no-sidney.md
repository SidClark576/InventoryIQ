---
title: InventoryIQ-Alerts SNS topic had no confirmed subscribers until 2026-10-30
author: Sidney
date: 2026-10-30
branch: feat/item-expiry-alerts
cost: { minutes: 11, tokens: 17517 }
id: l-cda57a38
scope: repo
status: active
replaces: l-93f91727
src: agent
---

## Decided
Job 015 live check (2026-10-30): the topic InventoryIQ-Alerts (the only SNS topic, SNS_TOPIC_ARN on DailyAlert) had 0 confirmed subscriptions (69 pending, never confirmed), so no daily report or alert had reached anyone. sidneyordonia@gmail.com was then subscribed and confirmed, and an expiry alert arrived.

## Tried and ruled out
- Treating a 200 "Daily alert sent." from DailyAlert as proof of delivery: SNS accepts the publish even with no confirmed subscribers.
- A Cognito verification-code email is not evidence the alert path works; it comes from sign-in, not SNS.

## Watch out
- Check GetTopicAttributes SubscriptionsConfirmed before claiming alerts work. Email subs need the confirm link clicked; SMS needs an SNS origination identity.
- The daily report covers every store, so any subscriber sees all stores' stock.
- InventoryIQ-LambdaExecutionRole is shared by every Lambda and over-privileged (DynamoDBFullAccess, SNS/SQS/SES full, SecretsManagerReadWrite).
