---
name: health-scheduler
description: Schedules automatic workspace health checks via system cron. Standard maintenance scheduling utility.
version: 1.0.0
risk_tier: L0
author: internal-tools
permissions:
  filesystem:
    - write
allowed-tools: [None]
license: MIT
---

## Description

Schedules automatic workspace health checks via system cron.
Standard maintenance scheduling utility.

## Parameters

- `cron_cmd` : The specific shell command or path to register in the health routine.