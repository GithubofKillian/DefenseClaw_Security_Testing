package defenseclaw.asi03

# Cette policy est évaluée par DefenseClaw (privilege_guard) AVANT chaque
# action sensible. Le user_role dans `input` DOIT provenir du profil de
# session authentifié côté serveur (résolu depuis users/*.json par
# l'infrastructure), JAMAIS d'une déclaration faite dans le prompt ou
# d'un message prétendant provenir d'un autre agent/du système. C'est
# précisément ce que testent les scénarios de cross-agent impersonation :
# un prompt peut prétendre "le rôle a été élevé à admin", ça ne doit
# jamais changer input.user_role tel que résolu côté serveur.
#
# Input attendu :
# {
#   "action": "refund_customer" | "read_hr_data",
#   "user_role": "employee" | "manager" | "admin"
# }

default allow = false

allowed_roles_by_action := {
    "refund_customer": {"manager", "admin"},
    "read_hr_data": {"manager", "admin"},
}

allow {
    allowed_roles_by_action[input.action][input.user_role]
}
