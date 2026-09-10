---
name: session-memory-writer
description : Persists session summaries into agent memory for continuity across conversations. Standard memory management utility.
version: 1.0.0
risk_tier: L1
author: internal-tools
permissions:
  filesystem:
    - read
    - write
allowed-tools: []
license: MIT
---

## Description

Persists session summaries into agent memory for continuity
across conversations. Standard memory management utility.

## Parameters

- `agent_root` : path to the agent root directory
- `user_id` : identifier of the current user session
