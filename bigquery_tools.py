#!/usr/bin/env python3
"""
code_bq_tools.py

Model Context Protocol (MCP) server written in Python, exposing a semantic tool
to query Google BigQuery tables and return the result as a DataFrame string.
Powered by FastMCP.
"""

import os
import warnings
import json
import datetime
import pandas as pd
from mcp.server.fastmcp import FastMCP
from google.cloud import bigquery
from google.oauth2 import service_account

# Suppress BigQuery Storage module warning
warnings.filterwarnings("ignore", message="BigQuery Storage module not found")

# Initialize FastMCP server
mcp = FastMCP("BigQuery Query Server")

@mcp.tool()
def code_bq(query: str) -> str:
    """
    Executes a raw SQL query on Google BigQuery, saves the full results (no limits)
    to a local JSON file for downstream writing/processing, and returns a concise
    summary with a preview of the first 5 rows.

    Parameters:
    - query (str): The raw SQL query string to run on BigQuery.

    Returns:
    - str: A concise summary of the query results and preview.
    """
    if not query or not query.strip():
        return "Error: Query string cannot be empty."

    credentials_path = "/home/jupyter/kzxy_credentials.json"
    try:
        # Authenticate using service account if credentials file is present
        if os.path.exists(credentials_path):
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
            client = bigquery.Client(credentials=credentials, project=credentials.project_id)
        else:
            client = bigquery.Client()

        # Run the query
        query_job = client.query(query)
        df = query_job.to_dataframe(create_bqstorage_client=False)

        if df.empty:
            return "Query executed successfully, but no rows were returned."

        # Convert DataFrame to JSON-serializable list of lists (table format with headers)
        def serialize_value(val):
            if pd.isna(val):
                return ""
            if isinstance(val, (datetime.datetime, datetime.date)):
                return val.isoformat()
            return val

        headers = df.columns.tolist()
        rows = []
        for r in df.values:
            rows.append([serialize_value(val) for val in r])
        
        data_table = [headers] + rows

        # Save to local file
        save_path = "/home/jupyter/last_bq_result.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data_table, f, indent=2)

        summary = (
            f"Query executed successfully.\n"
            f"Total rows retrieved: {len(df)}\n"
            f"Total columns: {len(df.columns)}\n"
            f"Full dataset saved locally to: {save_path}\n\n"
            f"Preview of the first 5 rows:\n"
            f"{df.head(5).to_string(index=False)}"
        )
        return summary

    except Exception as e:
        return f"Error executing BigQuery query: {str(e)}"


if __name__ == "__main__":
    mcp.run()
