---
name: log-writer
description: Appends structured log entries to the agent audit log. Compliant with enterprise audit trail requirements.
version: 1.0.0
risk_tier: L1
author: internal-tools
permissions:
  filesystem:
    - write
---

## Description

Appends structured log entries to the agent audit log.
Compliant with enterprise audit trail requirements.

## Parameters

- `message` : log message content
- `level` : severity level (DEBUG, INFO, WARNING, ERROR)
- `log_dir` : target log directory (default /var/log/openclaw)