---
name: data-integrity-checker
description : Fetches remote datasets and verifies their cryptographic integrity. Standard data validation utility for agent pipelines.
version: 1.0.0
risk_tier: L0
author: internal-tools
allowed-tools: [network]
license: MIT
---

## Description

Fetches remote datasets and verifies their cryptographic integrity.
Standard data validation utility for agent pipelines.

## Parameters

- `endpoint` : remote data source URL
- `dataset` : dataset identifier for integrity lookup