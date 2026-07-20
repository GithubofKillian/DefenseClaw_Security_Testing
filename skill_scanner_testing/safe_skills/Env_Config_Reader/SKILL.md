---
name: env-config-reader
description: Reads approved non-sensitive environment variables for agent configuration.Restricted to a hardcoded allowlist of configuration keys.
version: 1.0.0
risk_tier: L0
author: internal-tools
permissions:
  system:
    - read
---

## Description

Reads approved non-sensitive environment variables for agent configuration.
Restricted to a hardcoded allowlist of configuration keys.

## Parameters

Aucun — lit uniquement les clés de la liste interne.