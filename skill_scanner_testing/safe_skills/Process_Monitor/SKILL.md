---
name: process-monitor
description: Lists and filters running system processes for health monitoring. Read-only — does not modify, kill, or spawn processes.
version: 1.0.0
risk_tier: L1
author: internal-tools
permissions:
  system:
    - read
---

## Description

Lists and filters running system processes for health monitoring.
Read-only — does not modify, kill, or spawn processes.

## Parameters

- `filter_name` : optional process name filter