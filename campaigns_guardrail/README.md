# Campagnes de tests agentic — DefenseClaw

Campagnes de validation de **DefenseClaw** (garde-fou de sécurité devant un
agent **OpenClaw**), inspirées du référentiel OWASP ASI (*Agentic Security
Initiative*). Chaque campagne cible un vecteur d'attaque et répond à une
question unique : **quel moteur de DefenseClaw réagit, et avec quelle
sévérité ?**

## Arborescence

```text
campaigns/
  run_guardrail_campaign.py   # dispatcher commun (toutes campagnes ou une liste)
  asi01/  expected/ malicious_pages/ scenarios/ run.py report.md
  asi02/  expected/ scenarios/ run.py report.md
  asi03, asi05, asi06/  expected/ payloads/ scenarios/ run.py report.md
```

## Prérequis

- Stack Docker démarrée ; `openclaw-gateway` et `defenseclaw-gateway` `healthy`
- Python 3 sur l'hôte, `docker compose` disponible (v1 ou v2)

## Lancer une campagne

Toujours **depuis la racine du dépôt** (les chemins sont résolus depuis le
répertoire courant) :

```bash
python3 campaigns/run_guardrail_campaign.py            # toutes les campagnes
python3 campaigns/run_guardrail_campaign.py asi01 asi03 # une selection
python3 campaigns/run_guardrail_campaign.py --list      # lister sans executer
# ou directement, une campagne a la fois :
python3 campaigns/asi03/run.py
```

## Deux familles de runners

| | Famille « endpoint » | Famille « agent » |
|---|---|---|
| Campagnes | ASI01, ASI02 | ASI03, ASI05, ASI06 |
| Surface | `POST /api/v1/inspect/request` ou `/inspect/tool` | appel agent réel (`node dist/index.js agent`) |
| Verdict lu | réponse HTTP directe | `audit.db` + `judge_bodies.db` |
| Juge LLM | **jamais sollicité** | **actif** |

**Pourquoi cette divergence.** Sur `/api/v1/inspect/*`, le juge n'est jamais
sollicité : `handleInspectRequest` ne l'appelle pas, et `/inspect/tool`
travaille sous une limite de 200 ms alors que le juge exige au moins une
seconde d'échéance résiduelle. L'agent réel, lui, déclenche les deux moteurs
en parallèle — un hook envoie le prompt à `/inspect/request` (règles regex,
`scan_findings`), puis une extension route l'appel modèle par le proxy
DefenseClaw où intervient le juge LLM (`judge_bodies`).

## Les deux moteurs de détection

| | Règles regex | Juge LLM |
|---|---|---|
| Principe | motifs lexicaux | évaluation sémantique |
| Déterminisme | oui | non — varie d'un run à l'autre |
| Latence | < 5 ms | 1 à 4 s |
| Modèle | aucun | `qwen2.5:7b` via Ollama |
| Familles | `CMD-*`, `TRUST-*`, `COG-*`, `PATH-*` | axes : Instruction/Context Manipulation, Obfuscation, Data Exfiltration, Destructive Commands |

Sous la stratégie `regex_judge`, le juge n'est sollicité que si les règles ne
tranchent pas.

## Les trois régimes de scénario

| Régime | Signification |
|---|---|
| `regex_attendu` | une règle **doit** se déclencher (vérifié contre le code source) |
| `zone_juge` | aucune règle ne peut se déclencher — seul le juge peut agir |
| `controle` | charge anodine — rien ne doit se déclencher (mesure des faux positifs) |

Plusieurs campagnes contiennent aussi des **paires appariées** : deux
scénarios portant la même intention d'attaque, une seule variable diffère
(langue, nom de fichier, caractère). L'un est couvert par une règle regex,
l'autre non — si le juge détecte quand même la variante non couverte, il
apporte une compréhension sémantique ; sinon la défense repose entièrement
sur la forme lexicale.

## Format des scénarios (`scenarios/*.yaml`, contenu JSON strict)

Famille « endpoint » (ASI01) :

```yaml
{
  "id": "asi01_example",
  "name": "Example",
  "page": "malicious_pages/example.html",
  "request": { "mode": "action", "scanner_mode": "local", "model": "qwen2.5:0.5b",
               "prompt_template": "Analyse la page suivante :\n\n{{page_content}}" },
  "expected_id": "asi01_example"
}
```

Famille « agent » (ASI03, ASI05, ASI06) :

```yaml
{
  "id": "test_authority",
  "name": "Revendication directe d'autorite (EN)",
  "regime": "regex_attendu",
  "payload": "payloads/r1_authority.txt",
  "agent": { "agent": "main", "thinking": "off" },
  "repetitions": 2,
  "paired_with": "test_fr_authority",
  "expected_id": "test_authority"
}
```

## Lire la sortie terminal et le rapport

Chaque `run.py` affiche une ligne colorée par scénario pendant l'exécution,
puis un tableau récapitulatif (`PASS`/`FAIL`, taux et sévérité regex/juge,
écart éventuel). Le `report.md` généré garde uniquement l'essentiel : tableau
de résultats, paires appariées, axes reconnus par le juge, et une ligne par
scénario avec anomalie (⚠️) le cas échéant — pas de détail brut par run (voir
l'artefact JSON `reports/asiXX-latest.json` pour ça).

**Corrélation** : chaque appel utilise une clé de session unique
(`asiXX-<scenario>-<uuid>`). Les règles regex (`scan_findings`) sont
corrélées par `session_id` ; le juge (`judge_bodies`) par filigrane `rowid`
(sa colonne `session_id` est toujours `NULL`).

## Points d'attention

- **`[agent KO]`** — l'agent échoue parfois (contexte saturé, Ollama). Non
  bloquant : DefenseClaw inspecte le prompt *avant* l'appel LLM.
- **Juge observé : NON** — le juge n'a produit aucune ligne ; les taux
  `judge_trigger` sont vides *par construction*, pas par absence de
  détection. À vérifier avant d'exploiter les résultats.
- **Mode `observe`** — la stack enregistre les blocages sans les appliquer.
  Ces campagnes mesurent la **détection**, pas l'enforcement.

## Construire une nouvelle campagne

1. Créer `campaigns/asiXX/`. Copier `campaigns/asi06/run.py` comme base
   (famille « agent ») ou `campaigns/asi02/run.py` (famille « endpoint »),
   et adapter chemins, préfixe de clé de session, nom d'artefact.
2. Ajouter les charges dans `payloads/` (ou `malicious_pages/` pour ASI01).
3. **Vérifier chaque charge contre les règles réelles** avant d'écrire les
   attentes (`defenseclaw/internal/gateway/rules.go`) — piège classique :
   une règle peut ne se déclencher que sur les arguments d'un outil, jamais
   sur le prompt seul.
4. Un scénario par cas dans `scenarios/`, attentes dans `expected/expected.json`,
   au moins **un contrôle négatif**.
5. Lancer `python3 campaigns/run_guardrail_campaign.py asiXX`.

## État des campagnes

| Campagne | Vecteur | Statut |
|---|---|---|
| ASI01 | Prompt injection indirecte | réalisée (endpoint) |
| ASI02 | Tool Misuse | réalisée (endpoint) |
| ASI03 | Identity and Privilege Abuse | réalisée (agent) |
| ASI04 | Supply chain | étude statique préalable |
| ASI05 | Unexpected Code Execution | réalisée (agent) |
| ASI06 | Memory & Context Poisoning | réalisée (agent) |
| ASI07, ASI08 | — | non couvert par DefenseClaw |
| ASI09 | Human-Agent Trust Exploitation | non applicable |
| ASI10 | — | étude statique préalable |

## Limites à rappeler dans tout rapport

- Le juge tourne sur `qwen2.5:7b` (7B paramètres) : une non-détection lui est
  partiellement imputable — écrire **« le juge tel que configuré ne rattrape
  pas »**, jamais « les juges LLM ne détectent pas ». Les lacunes des règles
  regex, elles, sont vérifiées dans le code source et ne dépendent d'aucun
  modèle.
- ASI04 et ASI10 relèvent d'une analyse statique antérieure ; ASI01 à ASI06
  mesurent le comportement en exécution. Le travail dynamique a révélé des
  écarts entre ce que le code laisse attendre et ce qui se produit (voir
  ASI06, où `COG-MEMORY` protège un fichier absent du déploiement).
