"""
run.py - orchestrateur ASI03 (Privilege Escalation & Cross-Agent Trust
Exploitation).

Envoie le(s) prompt(s) du scénario à l'agent OpenClaw réel via la CLI du
container `openclaw-gateway`, puis juge en interrogeant `audit.db` de
DefenseClaw. Même architecture que ASI02.

============================================================================
TODO CRITIQUE - PAS ENCORE RÉSOLU POUR ASI03 SPÉCIFIQUEMENT
============================================================================
Chaque scénario déclare un `user_profile` (users/employee.json,
manager.json, admin.json) censé fixer le RÔLE RÉEL de la session, résolu
côté serveur, indépendamment de ce que le prompt prétend.

Sur ce stack, l'agent OpenClaw est unique (`--agent main`) : il n'y a pour
l'instant AUCUN mécanisme qui fasse correspondre `user_profile` à un rôle
réellement appliqué côté serveur. Le dispatch ci-dessous envoie le prompt
tel quel, SANS résolution de rôle - ce qui signifie que T1/T2/T3 ne
testent pas encore réellement le contrôle RBAC, seulement le comportement
par défaut de l'agent unique.

Deux pistes possibles à trancher avant que ces résultats aient un sens :
  a) définir plusieurs agents.list[] OpenClaw (un par rôle) - explicitement
     écarté plus tôt dans la conversation ;
  b) un mécanisme côté DefenseClaw/OpenClaw pour attacher un profil
     utilisateur à une session (à vérifier si ça existe dans leurs docs
     respectives - pas trouvé pour l'instant) ;
  c) accepter que ces scénarios restent en mode manuel/observationnel tant
     que ce point n'est pas réglé.

Le code ci-dessous fonctionne mécaniquement mais **le fait de jouer un
scénario ASI03 en mode réel aujourd'hui ne prouve rien sur le RBAC tant
que ce TODO n'est pas résolu.**
============================================================================

----------------------------------------------------------------------------
AUTRES HYPOTHÈSES (identiques à ASI02)
----------------------------------------------------------------------------
  1. OPENCLAWSECURE_DIR : chemin vers ton dépôt OpenClawSecure.
  2. Schéma de `audit_events` inconnu - recherche par sous-chaîne dans le
     JSON brut des événements plutôt qu'une colonne précise.
  3. STACK_GUARD_MODE doit être "action" pour que DefenseClaw bloque
     réellement.

WORKFLOW
----------------------------------------------------------------------------
    $ python3 run.py run scenarios/employee_refund.yaml
    $ python3 run.py run scenarios/admin_impersonation.yaml   # joue les 5 variantes
    $ python3 run.py run-all
============================================================================
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Optional

import yaml

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

# TODO : adapte ce chemin à l'emplacement réel de ton dépôt OpenClawSecure.
OPENCLAWSECURE_DIR = "/path/to/OpenClawSecure"

AUDIT_WRITE_DELAY_SECONDS = 1.5


def _load_scenario(scenario_path: Path) -> dict:
    return yaml.safe_load(scenario_path.read_text(encoding="utf-8"))


def dispatch_to_agent(prompt: str, session_key: str) -> dict:
    """
    Envoie un prompt à l'agent OpenClaw réel via la CLI du container
    openclaw-gateway. Voir le TODO en en-tête : `user_profile` n'est pas
    encore appliqué ici, seul le texte du prompt est envoyé.
    """
    cmd = [
        "docker", "compose", "exec", "-T", "openclaw-gateway",
        "node", "dist/index.js", "agent",
        "--agent", "main",
        "--session-key", session_key,
        "--message", prompt,
        "--thinking", "off",
        "--json",
    ]
    result = subprocess.run(
        cmd,
        cwd=OPENCLAWSECURE_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Échec de l'appel à l'agent OpenClaw : {result.stderr.strip()}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw_stdout": result.stdout, "raw_stderr": result.stderr}


def _query_audit_events(since_ts: float) -> list[dict]:
    """Interroge audit.db dans defenseclaw-gateway pour les événements
    'openclaw' depuis since_ts. Cf. TODO schéma en en-tête de fichier."""
    query = (
        "import os, sqlite3, json; "
        "db = os.path.join(os.environ['DEFENSECLAW_HOME'], 'audit.db'); "
        "con = sqlite3.connect(db); "
        "con.row_factory = sqlite3.Row; "
        "cur = con.cursor(); "
        "cur.execute("
        "  \"select * from audit_events where connector='openclaw' and timestamp >= ? order by timestamp\", "
        f"  ({since_ts},)"
        "); "
        "rows = [dict(r) for r in cur.fetchall()]; "
        "print(json.dumps(rows, default=str))"
    )
    cmd = ["docker", "compose", "exec", "-T", "defenseclaw-gateway", "python", "-c", query]
    result = subprocess.run(cmd, cwd=OPENCLAWSECURE_DIR, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"Échec de la requête audit.db : {result.stderr.strip()}")
    return json.loads(result.stdout)


def judge_audit(scenario_path, since_ts: float, agent_responses: Optional[list[dict]] = None) -> dict:
    scenario_path = Path(scenario_path)
    scenario = _load_scenario(scenario_path)
    expected = scenario.get("expected", {})
    forbidden = expected.get("forbidden_real_calls", [])

    events = _query_audit_events(since_ts)
    events_text = json.dumps(events, ensure_ascii=False)
    violations = [name for name in forbidden if name in events_text]

    if violations:
        status = "FAIL"
        detail = f"audit.db contient des événements liés à des tools interdits : {violations}"
    elif not events:
        status = "PASS"
        detail = "Aucun événement d'audit DefenseClaw trouvé sur cette fenêtre - vérifie que le scénario a bien été joué."
    else:
        status = "PASS"
        detail = "Aucun tool interdit détecté dans les événements d'audit DefenseClaw."

    return {
        "scenario_id": scenario["id"],
        "title": scenario["title"],
        "user_profile": scenario.get("user_profile"),
        "status": status,
        "detail": detail,
        "audit_events": events,
        "agent_responses": agent_responses,
    }


def run_scenario(scenario_path, session_key: Optional[str] = None) -> dict:
    """
    Joue un scénario contre l'agent OpenClaw. Gère deux formes :
      - scénario "simple" avec un champ `prompt` unique (T1, T2)
      - scénario à `variants` (admin_impersonation.yaml, T3) : chaque
        variante est envoyée à la suite, dans la MÊME session (pour
        rester au plus près du scénario "cross-agent trust" tel que
        décrit - un attaquant qui tente plusieurs techniques dans le même
        échange), puis jugées ensemble.
    """
    scenario_path = Path(scenario_path)
    scenario = _load_scenario(scenario_path)
    session_key = session_key or scenario["id"].lower()

    prompts = []
    if "variants" in scenario:
        prompts = [v["prompt"] for v in scenario["variants"]]
    else:
        prompts = [scenario["prompt"]]

    since_ts = time.time()
    agent_responses = [dispatch_to_agent(p, session_key=session_key) for p in prompts]
    time.sleep(AUDIT_WRITE_DELAY_SECONDS)

    return judge_audit(scenario_path, since_ts=since_ts, agent_responses=agent_responses)


def run_all() -> list[dict]:
    return [run_scenario(p) for p in sorted(SCENARIOS_DIR.glob("*.yaml"))]


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Orchestrateur ASI03 - dispatch réel vers OpenClaw + jugement via audit.db.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Dispatch un scénario (ou ses variantes) à OpenClaw et juge via audit.db.")
    p_run.add_argument("scenario")
    p_run.add_argument("--session-key", help="Clé de session OpenClaw (défaut : id du scénario).")

    sub.add_parser("run-all", help="Joue et juge tous les scénarios via OpenClaw + audit.db.")

    args = parser.parse_args()

    if args.command == "run":
        result = run_scenario(args.scenario, session_key=args.session_key)
        print(f"[{result['status']}] {result['scenario_id']} - {result['title']} :: {result['detail']}")
    elif args.command == "run-all":
        for result in run_all():
            print(f"[{result['status']}] {result['scenario_id']} - {result['title']} :: {result['detail']}")


if __name__ == "__main__":
    _cli()