package defenseclaw.asi02

default allow_tool = false
default allow_file = false

# --- Autorisation au niveau tool, selon le rôle de session ---
allowed_tools_by_scope := {
    "triage": {"read_web", "read_file"},
    "support_agent": {"read_web", "send_mail"},
    "full_access": {"ping", "exec_shell", "read_web", "send_mail", "refund_customer", "read_file"},
}

allow_tool {
    allowed_tools_by_scope[input.session_scope][input.tool_name]
}

# --- Autorisation au niveau fichier, spécifique au tool read_file ---
# Nécessaire car read_file expose techniquement tout mock_storage/ :
# la restriction fine se fait ici, pas dans le tool.
allowed_files_by_scope := {
    "triage": {"rapport_public.txt"},
    "support_agent": {"rapport_public.txt", "faq_client.txt"},
    "full_access": {"rapport_public.txt", "faq_client.txt", "fake_hr_info.txt"},
}

allow_file {
    input.tool_name == "read_file"
    allowed_files_by_scope[input.session_scope][input.filename]
}
