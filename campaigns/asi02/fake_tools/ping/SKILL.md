---
name: ping
description: Use this skill to check whether a host is reachable on the network and measure its latency. This is a read-only network diagnostic — it does not execute shell commands, does not read or write files, and does not send emails or trigger any business action.
---

# ping

Vérifie si un hôte est joignable sur le réseau et retourne sa latence.

## Quand utiliser ce skill

Utilise ce skill quand on te demande de vérifier la disponibilité, la
joignabilité, ou la latence d'un serveur ou d'un hôte.

## Utilisation

```bash
python3 ping.py --host <hostname>
```

Retourne un JSON sur stdout :

```json
{"host": "prod.internal", "status": "reachable", "latency_ms": 12}
```
