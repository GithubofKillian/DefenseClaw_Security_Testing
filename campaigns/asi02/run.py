#!/usr/bin/env python3
"""ASI02 - Tool Misuse.

Question evaluee :
    "DefenseClaw bloque-t-il correctement un outil interdit dans ses
     politiques statiques ?"

Methodologie (calquee sur campaigns/asi01/run.mjs) : on interroge directement
le moteur d'admission d'outil de DefenseClaw via POST /api/v1/inspect/tool,
sans passer par l'agent. Pour chaque scenario le runner place l'outil sur la
block-list statique (POST /enforce/block), soumet l'appel d'outil qu'un agent
detourne aurait emis, puis verifie que le verdict est un refus portant le
finding STATIC-BLOCK.

Le verdict attendu est rendu a l'etage 1 de la cascade de decision (politique
statique), avant toute analyse des arguments et avant le juge LLM : la
campagne est donc deterministe et insensible au plafond de 200 ms du juge.

Portee : la campagne mesure uniquement la direction positive (un outil
interdit est-il refuse). Elle ne verifie pas qu'un outil non interdit reste
autorise ; limite rappelee dans le rapport genere.

Note d'implementation : DefenseClaw n'ecoute que sur la loopback DU CONTENEUR
(127.0.0.1:18970) car compose declare `expose` et non `ports`. Le port n'est
donc pas joignable depuis l'hote. Ce script orchestre en Python mais fait
executer chaque requete HTTP par le Node present DANS le conteneur
openclaw-gateway, via `docker compose exec`. Aucun Node n'est requis sur
l'hote, et seule la bibliotheque standard Python est utilisee.

Usage :
    cd /chemin/vers/OpenClawSecure-main
    python3 campaigns/asi02/run.py
"""

import base64
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path.cwd()
CAMPAIGN_DIR = REPO_ROOT / "campaigns" / "asi02"
SCENARIOS_DIR = CAMPAIGN_DIR / "scenarios"
EXPECTED_FILE = CAMPAIGN_DIR / "expected" / "expected.json"
REPORT_FILE = CAMPAIGN_DIR / "report.md"
RESULTS_FILE = REPO_ROOT / "reports" / "asi02-latest.json"

SIDECAR = "http://127.0.0.1:18970"
CLIENT = "asi02-runner"
SERVICE = "openclaw-gateway"
TIMEOUT_RETRIES = 3
TIMEOUT_BACKOFF_S = 0.4

SEVERITY_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


class RunnerError(RuntimeError):
    """Erreur d'execution du runner."""


# --------------------------------------------------------------------------
# Acces au sidecar DefenseClaw
# --------------------------------------------------------------------------

_COMPOSE_CMD = None


def compose_cmd():
    """Detecte `docker compose` (v2) ou `docker-compose` (v1)."""
    global _COMPOSE_CMD
    if _COMPOSE_CMD is not None:
        return _COMPOSE_CMD
    for candidate in (["docker", "compose"], ["docker-compose"]):
        try:
            probe = subprocess.run(
                candidate + ["version"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                _COMPOSE_CMD = candidate
                return _COMPOSE_CMD
        except FileNotFoundError:
            continue
    raise RunnerError(
        "Ni `docker compose` ni `docker-compose` n'est disponible sur l'hote."
    )


# Script Node execute A L'INTERIEUR du conteneur. Il recoit la requete encodee
# en base64 pour eviter tout probleme de quoting shell.
NODE_SCRIPT = """
const p = JSON.parse(Buffer.from(process.argv[1], 'base64').toString('utf8'));
const init = {
  method: p.method,
  headers: {
    'Content-Type': 'application/json',
    'X-DefenseClaw-Token': process.env.OPENCLAW_GATEWAY_TOKEN,
    'X-DefenseClaw-Client': p.client
  }
};
if (p.body !== null) { init.body = JSON.stringify(p.body); }
fetch(p.url, init).then(async (r) => {
  const text = await r.text();
  if (!r.ok) { console.error('HTTP ' + r.status + ': ' + text); process.exit(2); }
  process.stdout.write(text);
}).catch((e) => { console.error(String(e)); process.exit(1); });
"""


def sidecar_fetch(url, method="GET", body=None):
    """Execute une requete HTTP vers DefenseClaw depuis le conteneur."""
    payload = base64.b64encode(
        json.dumps(
            {"method": method, "url": url, "body": body, "client": CLIENT}
        ).encode("utf8")
    ).decode("ascii")

    result = subprocess.run(
        compose_cmd()
        + ["exec", "-T", SERVICE, "node", "-e", NODE_SCRIPT, payload],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RunnerError(message or "docker compose exec a echoue")
    return result.stdout.strip()


def sidecar_json(url, method="GET", body=None):
    raw = sidecar_fetch(url, method=method, body=body)
    if not raw:
        raise RunnerError(f"Reponse vide de {url}")
    return json.loads(raw)


# --------------------------------------------------------------------------
# Operations DefenseClaw
# --------------------------------------------------------------------------


def get_guardrail_config():
    return sidecar_json(f"{SIDECAR}/v1/guardrail/config")


def set_guardrail_config(config):
    return sidecar_json(
        f"{SIDECAR}/v1/guardrail/config", method="PATCH", body=config
    )


def enforce_block(tool):
    sidecar_fetch(
        f"{SIDECAR}/enforce/block",
        method="POST",
        body={
            "target_type": "tool",
            "target_name": tool,
            "reason": "asi02 - outil hors perimetre",
        },
    )


def enforce_unblock(tool):
    sidecar_fetch(
        f"{SIDECAR}/enforce/block",
        method="DELETE",
        body={
            "target_type": "tool",
            "target_name": tool,
            "reason": "asi02 teardown",
        },
    )


def inspect_tool_once(scenario):
    request = scenario["request"]
    return sidecar_json(
        f"{SIDECAR}/api/v1/inspect/tool",
        method="POST",
        body={
            "tool": request["tool"],
            "args": json.dumps(request.get("args", {})),
        },
    )


def inspect_tool(scenario):
    """Appelle /inspect/tool avec retry sur `scan timeout`.

    L'endpoint applique un delai maximal de 200 ms non configurable et renvoie
    504 {"error":"scan timeout"} sans repli. Nos scenarios se resolvent a
    l'etage politique (sans LLM) : un timeout traduit au pire un demarrage a
    froid, donc on retente avec un backoff progressif.
    """
    last_error = None
    for attempt in range(TIMEOUT_RETRIES + 1):
        try:
            return inspect_tool_once(scenario)
        except RunnerError as error:
            last_error = error
            text = str(error)
            if "scan timeout" not in text and "504" not in text:
                raise
            time.sleep(TIMEOUT_BACKOFF_S * (attempt + 1))
    raise RunnerError(
        f"inspect/tool a expire pour {scenario['id']} : {last_error}"
    )


def warmup():
    """Amortit le demarrage a froid avant la boucle de mesure."""
    try:
        sidecar_fetch(
            f"{SIDECAR}/api/v1/inspect/tool",
            method="POST",
            body={"tool": "noop_warmup", "args": "{}"},
        )
    except RunnerError:
        pass  # best-effort : chaque scenario porte son propre retry


# --------------------------------------------------------------------------
# Comparaison des verdicts
# --------------------------------------------------------------------------


def finding_matches(findings, expected_prefixes):
    if not expected_prefixes:
        return True
    return any(
        finding == prefix or finding.startswith(f"{prefix}:")
        for finding in findings
        for prefix in expected_prefixes
    )


def compare_verdict(verdict, expectation):
    action_ok = verdict.get("action") in expectation["accepted_actions"]
    severity_ok = SEVERITY_RANK.get(verdict.get("severity"), -1) >= SEVERITY_RANK.get(
        expectation["min_severity"], 99
    )
    finding_ok = finding_matches(
        verdict.get("findings") or [], expectation.get("required_findings_any")
    )
    return {
        "pass": action_ok and severity_ok and finding_ok,
        "action_ok": action_ok,
        "severity_ok": severity_ok,
        "finding_ok": finding_ok,
    }


def reasoning_for(comparison):
    if comparison["pass"]:
        return "DefenseClaw a refuse l'admission de l'outil interdit (block statique)."
    if not comparison["action_ok"]:
        return "Action plus permissive qu'attendu : l'outil interdit n'a pas ete refuse."
    if not comparison["severity_ok"]:
        return "Severite observee inferieure au seuil attendu."
    if not comparison["finding_ok"]:
        return (
            "Refus obtenu mais sans le finding STATIC-BLOCK : la decision ne vient "
            "pas de la politique statique."
        )
    return "Ecart non classifie."


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------


def build_report(results, original_config, campaign_config, blocked_tools):
    pass_count = sum(1 for r in results if r["comparison"]["pass"])
    lines = [
        "# ASI02 - Tool Misuse",
        "",
        "## Question evaluee",
        "",
        "DefenseClaw bloque-t-il correctement un outil interdit dans ses politiques statiques ?",
        "",
        "## Conditions d'execution",
        "",
        f"- Date : {datetime.now(timezone.utc).isoformat()}",
        f"- Mode DefenseClaw initial : {original_config.get('mode')}/{original_config.get('scanner_mode')}",
        f"- Mode impose pour la campagne : {campaign_config['mode']}/{campaign_config['scanner_mode']}",
        f"- Outils places sur la block-list : {', '.join(blocked_tools) or 'aucun'}",
        f"- Resultat global : {pass_count}/{len(results)} scenarios conformes",
        "",
        "## Methodologie",
        "",
        "La campagne interroge directement le moteur d'admission d'outil de DefenseClaw",
        "via `POST /api/v1/inspect/tool`, sans passer par l'agent. Pour chaque scenario,",
        "le runner place l'outil vise sur la block-list statique (`POST /enforce/block`),",
        "soumet l'appel d'outil qu'un agent detourne aurait emis, puis compare le verdict",
        "aux attentes declarees dans `expected/expected.json`.",
        "",
        "Le verdict attendu (`block` / `HIGH` / `STATIC-BLOCK`) est rendu a l'etage 1 de",
        "la cascade de decision, c'est-a-dire avant toute analyse des arguments et avant",
        "le juge LLM. La campagne est donc deterministe.",
        "",
        "Le runner orchestre depuis l'hote en Python, mais delegue chaque requete HTTP au",
        "Node embarque dans le conteneur openclaw-gateway : le port 18970 de DefenseClaw",
        "est declare `expose` et non `ports`, il n'est donc pas joignable depuis l'hote.",
        "",
        "En fin d'execution, le runner retire les blocages et restaure la configuration",
        "d'origine, y compris en cas d'erreur.",
        "",
        "## Resultats",
        "",
        "| Scenario | Outil | Attendu | Observe | Findings | Verdict |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        scenario = r["scenario"]
        verdict = r["verdict"]
        expectation = r["expectation"]
        expected = (
            f"{'/'.join(expectation['accepted_actions'])} >= {expectation['min_severity']}"
        )
        observed = f"{verdict.get('action')} / {verdict.get('severity')}"
        findings = ", ".join(verdict.get("findings") or []) or "aucun"
        status = "PASS" if r["comparison"]["pass"] else "FAIL"
        lines.append(
            f"| {scenario['id']} | `{scenario['request']['tool']}` | {expected} | "
            f"{observed} | {findings} | {status} |"
        )

    lines += ["", "## Detail par scenario", ""]
    for r in results:
        scenario = r["scenario"]
        verdict = r["verdict"]
        lines.append(f"### {scenario['id']} - {scenario['name']}")
        lines.append("")
        lines.append(f"- Vecteur : {scenario.get('vector', 'n/a')}")
        lines.append(f"- Outil cible : `{scenario['request']['tool']}`")
        lines.append(f"- Action : `{verdict.get('action')}`")
        lines.append(
            f"- Raw action : `{verdict.get('raw_action', verdict.get('action'))}`"
        )
        lines.append(f"- Severite : `{verdict.get('severity')}`")
        lines.append(
            f"- Findings : {', '.join(verdict.get('findings') or []) or 'aucun'}"
        )
        lines.append(f"- Raison renvoyee : {verdict.get('reason', 'n/a')}")
        lines.append(f"- Interpretation : {reasoning_for(r['comparison'])}")
        lines.append("")

    lines += [
        "## Portee et limites",
        "",
        "- La campagne mesure uniquement la direction positive : un outil interdit est-il "
        "refuse. Elle ne verifie pas qu'un outil non interdit reste autorise, choix de "
        "perimetre assume.",
        "- Le blocage porte sur la CAPACITE (l'outil entier), pas sur ses arguments : "
        "`read_file` est refuse quel que soit le chemin demande. Le scope par fichier "
        "n'est pas exprimable par une block-list d'outils.",
        "- Les verdicts refletent la block-list injectee par le runner, retiree en fin "
        "de campagne.",
        "- DefenseClaw ne porte aucune dimension d'identite (role, utilisateur, session) "
        "dans sa decision : sa granularite maximale est `(connecteur, outil)`. Une "
        "politique d'outil s'applique donc a l'installation entiere.",
        "- La campagne evalue l'admission d'outil, pas l'execution reelle par l'agent : "
        "elle ne dit pas si un agent tenterait effectivement cet appel.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Point d'entree
# --------------------------------------------------------------------------


def load_scenarios():
    """Charge les scenarios (JSON dans des fichiers .yaml, pas de PyYAML requis)."""
    scenarios = []
    for path in sorted(SCENARIOS_DIR.glob("*.yaml")):
        try:
            scenarios.append(json.loads(path.read_text(encoding="utf8")))
        except json.JSONDecodeError as error:
            raise RunnerError(f"Scenario illisible {path.name} : {error}") from error
    if not scenarios:
        raise RunnerError(f"Aucun scenario trouve dans {SCENARIOS_DIR}")
    return scenarios


def main():
    if not CAMPAIGN_DIR.is_dir():
        raise RunnerError(
            f"{CAMPAIGN_DIR} introuvable. Lancez le script depuis la racine du depot."
        )

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf8"))
    scenarios = load_scenarios()

    blocked_tools = []
    for scenario in scenarios:
        for tool in scenario.get("setup", {}).get("block_tools", []):
            if tool not in blocked_tools:
                blocked_tools.append(tool)

    original_config = get_guardrail_config()
    campaign_config = {"mode": "action", "scanner_mode": "local"}
    restore_needed = (
        original_config.get("mode") != campaign_config["mode"]
        or original_config.get("scanner_mode") != campaign_config["scanner_mode"]
    )

    results = []

    if restore_needed:
        set_guardrail_config(campaign_config)
    for tool in blocked_tools:
        enforce_block(tool)

    try:
        warmup()
        for scenario in scenarios:
            expectation = expected.get(scenario["expected_id"])
            if expectation is None:
                raise RunnerError(
                    f"Attente manquante pour {scenario['expected_id']}"
                )
            verdict = inspect_tool(scenario)
            results.append(
                {
                    "scenario": scenario,
                    "expectation": expectation,
                    "verdict": verdict,
                    "comparison": compare_verdict(verdict, expectation),
                }
            )
    finally:
        for tool in blocked_tools:
            try:
                enforce_unblock(tool)
            except RunnerError as error:
                print(f"WARN: echec du deblocage de {tool} : {error}", file=sys.stderr)
        if restore_needed:
            try:
                set_guardrail_config(original_config)
            except RunnerError as error:
                print(
                    f"WARN: echec de la restauration de la config : {error}",
                    file=sys.stderr,
                )

    REPORT_FILE.write_text(
        build_report(results, original_config, campaign_config, blocked_tools),
        encoding="utf8",
    )
    RESULTS_FILE.write_text(
        json.dumps(
            {
                "campaign": "asi02",
                "question": "DefenseClaw bloque-t-il un outil interdit par politique statique ?",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "original_config": original_config,
                "enforced_config": campaign_config,
                "blocked_tools": blocked_tools,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf8",
    )

    pass_count = sum(1 for r in results if r["comparison"]["pass"])
    print(f"ASI02 complete: {pass_count}/{len(results)} scenarios met the expectation.")
    print(f"Report: {REPORT_FILE.relative_to(REPO_ROOT)}")
    print(f"Artifact: {RESULTS_FILE.relative_to(REPO_ROOT)}")
    return 0 if pass_count == len(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RunnerError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrompu.", file=sys.stderr)
        sys.exit(130)