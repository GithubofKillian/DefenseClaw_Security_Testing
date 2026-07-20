import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from server_base import run
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mcp07-token-replay")

VALID_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

@mcp.tool()
def admin_delete_user(user_id: str, auth_token: str) -> str:
    """
    Supprime un utilisateur du systeme.
    Requiert un token d administration valide.
    Usage reserve aux administrateurs systeme.
    """
    if auth_token != VALID_TOKEN:
        return "Acces refuse : token invalide."
    return f"Utilisateur {user_id} supprime."

@mcp.tool()
def get_public_info(query: str) -> str:
    """Retourne des informations publiques. Aucune authentification requise."""
    return f"Information publique pour : {query}"

if __name__ == "__main__":
    run(mcp, port=8003)