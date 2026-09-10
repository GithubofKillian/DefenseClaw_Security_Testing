---
name: web-fetcher
description: Fetches content from approved external URLs for data retrieval. Restricted to a configurable domain allowlist.
version: 1.0.0
risk_tier: L1
author: internal-tools
permissions:
  network:
    - outbound
---

## Description

Fetches content from approved external URLs for data retrieval.
Restricted to a configurable domain allowlist.

## Parameters

- `url` : target URL (must be in allowlist)
- `timeout` : request timeout in seconds (default 10)