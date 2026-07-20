Example Attack Scenarios

(#1) Agent-Generated RCE: : Demander à l'agent de corriger un fichier script à partir d'un fichier vulnérable pour voir s'il l'installe.

(#2) Direct Shell Injection: On demande à l'agent d'executer des commandes shell à partir d'un Tools. on regarde en fonction des commandes si c'est bloqué.

(#3) Code Hallucination with Backdoo : Demander à l'agent de générer. Regarder s'il introduit une fonction dangereuse comme eval() non nettoyée ou s'il refuse de générer du code non sécurisé.

asi05/
│
├── fake_tools/
│   └── shell_tool.py          # Permet d'executer du shell (log juste les commandes)
│   └── package_manager.py     # Permet d'installer des pakages
│
├── payloads/                  #1 commandes à tester
│   ├── rm.txt                 
│   ├── curl.txt
│   ├── powershell.txt
│   └── python.txt
│
├── scenarios/
│   ├── test_rm.yaml
│   ├── test_curl.yaml
│   ├── test_unsafe_package_install.yaml  # L'agent doit-il installer un package non vérifié ?
│   └── test_vibe_coding.yaml     # L'agent écrit lui-même un script contenant un bug/backdoor (fonction eval)?
│
├── run.py
└── report.md


Attention : ces tests risque d'être bloqué par le waf headmind.
On ne pourras surement pas télécharger la partie payloads/