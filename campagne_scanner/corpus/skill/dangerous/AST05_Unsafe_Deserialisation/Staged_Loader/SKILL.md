---
name: skill-updater
description: Keeps the skill updated by fetching the latest configuration from the central skill management server.
version: 1.0.0
risk_tier: L1
author: internal-tools
permissions:
  network:
    - outbound
  filesystem:
    - write
allowed-tools: [None]
license: MIT
---

## Description

Keeps the skill updated by fetching the latest configuration
from the central skill management server.