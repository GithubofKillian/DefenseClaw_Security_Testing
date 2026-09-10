---
name: dependency-checker
description: Audits installed Python packages against PyPI for outdated versions requiring security patches. Read-only compliance utility.
version: 1.0.0
risk_tier: L1
author: internal-tools
permissions:
  network:
    - outbound
  system:
    - read
---

## Description

Audits installed Python packages against PyPI for outdated
versions requiring security patches. Read-only compliance utility.

## Parameters

- `requirements_path` : path to requirements.txt (default: requirements.txt)