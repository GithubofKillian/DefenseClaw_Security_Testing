def run(query: str) -> dict:
    """
    Returns a formatted query result.
    Standard data processing utility.
    """
    processed_query = query.strip().lower()
    
    return {
        "status": "processed",
        "output": f"result:{processed_query}"
    }