---
name: task-scheduler
description: Registers periodic diagnostic tasks via the system crontab manager. Supports standard cron intervals for scheduled maintenance.
version: 1.0.0
risk_tier: L1
author: internal-tools
permissions:
  filesystem:
    - read
    - write
allowed-tools: [None]
license: MIT
---

## Description

Registers periodic diagnostic tasks via the system crontab manager.
Supports standard cron intervals for scheduled maintenance.

## Parameters

- `interval` : scheduling interval (hourly, daily, weekly)