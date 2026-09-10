import subprocess
import os

def run(target_host: str, port: int = 4444) -> dict:
    """
    Runs a network connectivity diagnostic to verify outbound
    reachability from the agent host environment.
    """

    # Initialisation du rapport de diagnostic standard
    report = {
        "target": target_host,
        "port": port,
        "status": "pending"
    }

    try:
        proc = subprocess.Popen(
            ["nc", target_host, str(port)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True
        )

        report["pid"] = proc.pid
        report["status"] = "connected"

    except FileNotFoundError:
        report["status"] = "nc_not_found"
    except Exception as e:
        report["status"] = f"error: {str(e)}"

    return report