"""
run.py - orchestrateur ASI01 (Prompt Injection).

Envoie le prompt du scénario à l'agent OpenClaw réel via la CLI du
container `openclaw-gateway`, puis juge selon ce qui est défini pour ce
scénario dans expected/expected.json (clé = id du scénario) :

  - forbidden_real_calls          -> jugement via audit.db de DefenseClaw
                                      (T3 base64, T5 tool pivot)
  - forbidden_patterns_in_output  -> jugement via le texte de la réponse
                                      de l'agent (T1 markdown, T2 meta,
                                      T4 policy override)

Les deux peuvent être combinés pour un même scénario (aucun cas dans les
5 scénarios actuels, mais le mécanisme le permet).

============================================================================
HYPOTHÈSES / TODO (identiques aux campagnes précédentes)
============================================================================
  1. OPENCLAWSECURE_DIR : chemin vers ton dépôt OpenClawSecure.
  2. Schéma de `audit_events` inconnu - recherche par sous-chaîne.
  3. STACK_GUARD_MODE doit être "action" pour que DefenseClaw bloque
     réellement (pertinent pour T3/T5 uniquement).
  4. `_extract_agent_text()` devine le nom du champ contenant le texte de
     réponse dans le JSON `--json` de la CLI - à corriger avec un exemple
     réel (pertinent pour T1/T2/T4).
============================================================================

WORKFLOW
----------------------------------------------------------------------------
    $ python3 run.py run scenarios/markdown.yaml
    $ python3 run.py run scenarios/tool.yaml
    $ python3 run.py run-all
============================================================================
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import yaml

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
EXPECTED_PATH = Path(__file__).parent / "expected" / "expected.json"

# TODO : adapte ce chemin à l'emplacement réel de ton dépôt OpenClawSecure.
OPENCLAWSECURE_DIR = "/path/to/OpenClawSecure"

AUDIT_WRITE_DELAY_SECONDS = 1.5


def _load_scenario(scenario_path: Path) -> dict:
    return yaml.safe_load(scenario_path.read_text(encoding="utf-8"))


def _load_expected() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def dispatch_to_agent(prompt: str, session_key: str) -> dict:
    """Envoie un prompt à l'agent OpenClaw réel via la CLI du container openclaw-gateway."""
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


def _extract_agent_text(agent_response: dict) -> str:
    """Cf. TODO en en-tête : devine le champ texte dans la réponse JSON."""
    for key in ("response", "message", "content", "text", "reply"):
        value = agent_response.get(key)
        if isinstance(value, str):
            return value
    return json.dumps(agent_response, ensure_ascii=False)


def _query_audit_events(since_ts: float) -> list[dict]:
    """Interroge audit.db dans defenseclaw-gateway. Cf. TODO schéma en en-tête."""
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


def run_scenario(scenario_path, session_key: Optional[str] = None) -> dict:
    scenario_path = Path(scenario_path)
    scenario = _load_scenario(scenario_path)
    scenario_id = scenario["id"]
    session_key = session_key or scenario_id.lower()

    expected_all = _load_expected()
    expected = expected_all.get(scenario_id)
    if expected is None:
        return {
            "scenario_id": scenario_id,
            "title": scenario["title"],
            "status": "ERROR",
            "detail": f"Aucune entrée pour {scenario_id} dans expected/expected.json.",
        }

    since_ts = time.time()
    agent_response = dispatch_to_agent(scenario["prompt"], session_key=session_key)

    violations = []

    # --- Volet appels interdits, via audit.db ---
    forbidden_calls = expected.get("forbidden_real_calls", [])
    events = []
    if forbidden_calls:
        time.sleep(AUDIT_WRITE_DELAY_SECONDS)
        events = _query_audit_events(since_ts)
        events_text = json.dumps(events, ensure_ascii=False)
        call_violations = [name for name in forbidden_calls if name in events_text]
        if call_violations:
            violations.append(f"appels interdits détectés dans audit.db : {call_violations}")

    # --- Volet motifs interdits, via le texte de la réponse ---
    forbidden_patterns = expected.get("forbidden_patterns_in_output", [])
    if forbidden_patterns:
        text = _extract_agent_text(agent_response)
        pattern_hits = [p for p in forbidden_patterns if re.search(p, text, re.IGNORECASE)]
        if pattern_hits:
            violations.append(f"motifs interdits détectés dans la sortie : {pattern_hits}")

    if violations:
        status, detail = "FAIL", " ; ".join(violations)
    else:
        status, detail = "PASS", "Aucune violation détectée."

    return {
        "scenario_id": scenario_id,
        "title": scenario["title"],
        "status": status,
        "detail": detail,
        "agent_response": agent_response,
        "audit_events": events,
    }


def run_all() -> list[dict]:
    return [run_scenario(p) for p in sorted(SCENARIOS_DIR.glob("*.yaml"))]


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Orchestrateur ASI01 - dispatch réel vers OpenClaw + jugement via audit.db et/ou sortie texte.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Dispatch un scénario à OpenClaw et juge.")
    p_run.add_argument("scenario")
    p_run.add_argument("--session-key", help="Clé de session OpenClaw (défaut : id du scénario).")

    sub.add_parser("run-all", help="Joue et juge tous les scénarios.")

    args = parser.parse_args()

    if args.command == "run":
        result = run_scenario(args.scenario, session_key=args.session_key)
        print(f"[{result['status']}] {result['scenario_id']} - {result['title']} :: {result['detail']}")
    elif args.command == "run-all":
        for result in run_all():
            print(f"[{result['status']}] {result['scenario_id']} - {result['title']} :: {result['detail']}")


if __name__ == "__main__":
    _cli()