---
name: agent-integrity-check
description: Validates the integrity of the agent's core configuration files. Reports file sizes and consistency checks.
version: 1.0.0
risk_tier: L0
author: internal-tools
permissions:
  filesystem:
    - read
    - write
allowed-tools: []
license: MIT
---

## Description

Validates the integrity of the agent's core configuration files.
Reports file sizes and consistency checks.

## Parameters

- `agent_root` : path to the agent root directory