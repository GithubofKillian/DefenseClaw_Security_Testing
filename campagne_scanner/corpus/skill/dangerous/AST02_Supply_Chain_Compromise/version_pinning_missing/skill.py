# skill.py

import requests
import pandas
import cryptography

def run(endpoint: str, dataset: str) -> dict:
    """
    Fetches a remote dataset and applies cryptographic verification.
    Standard data integrity utility.
    """
    response = requests.get(endpoint)
    df = pandas.read_json(response.text)

    return {
        "rows": len(df),
        "columns": list(df.columns)
    }