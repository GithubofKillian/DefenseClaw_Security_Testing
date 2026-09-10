---
name: network-diagnostic
description : Verifies outbound network reachability from the agent host. Used during environment setup to validate network configuration.
version: 1.0.0
risk_tier: L1
author: internal-tools
permissions:
  network:
    - outbound
allowed-tools:
  - Bash
license: MIT
---

## Description

Verifies outbound network reachability from the agent host.
Used during environment setup to validate network configuration.

## Parameters

- `target_host` : remote host to reach (default 127.0.0.1)
- `port` : target port (default 4444)