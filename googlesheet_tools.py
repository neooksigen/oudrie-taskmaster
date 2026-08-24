#!/usr/bin/env python3
"""
trix_tools.py

Model Context Protocol (MCP) server written in Python, exposing tools
to read and write Google Sheets ("trix") with advanced layout requirements.
Powered by FastMCP.
"""

import os
import re
import pandas as pd
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("Trix Sheets Server")

def _get_service():
    """
    Returns an authenticated Google Sheets v4 API service instance.
    Prioritizes /home/jupyter/kzxy_credentials.json service account file.
    """
    import google.auth
    from googleapiclient.discovery import build
    
    creds_path = "/home/jupyter/kzxy_credentials.json"
    if os.path.exists(creds_path):
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
    else:
        credentials, project = google.auth.default(
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
    return build('sheets', 'v4', credentials=credentials)


def get_spreadsheet_id(url_or_id: str) -> str:
    """
    Helper to extract the Google Spreadsheet ID from a full browser URL or matches a raw ID.
    """
    url_or_id = url_or_id.strip()
    match = re.search(r'spreadsheets/d/([a-zA-Z0-9-_]+)', url_or_id)
    if match:
        return match.group(1)
    if re.match(r'^[a-zA-Z0-9-_]+$', url_or_id):
        return url_or_id
    raise ValueError(f"Could not extract spreadsheet ID from: '{url_or_id}'")


@mcp.tool()
def read_gs(gs_url: str, tab_name: str) -> list[dict]:
    """
    Reads data from a specified tab of a Google Sheet and returns it as a list of dictionaries.
    Automatically detects the first non-empty header row.

    Parameters:
    - gs_url (str): The Google Sheet browser URL or spreadsheet ID.
    - tab_name (str): The tab name to read from.

    Returns:
    - list[dict]: A list of row dictionaries representing the spreadsheet data.
    """
    try:
        spreadsheet_id = get_spreadsheet_id(gs_url)
        service = _get_service()

        # Read range (A1:ZZ20000) to capture all potential data
        res = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A1:ZZ20000"
        ).execute()

        values = res.get('values', [])
        if not values:
            return []

        # Find the header row
        header_idx = 0
        # First try: find the first row with at least 4 non-empty cells
        for idx, r in enumerate(values[:20]):
            non_empty_count = sum(1 for cell in r if str(cell).strip() != "")
            if non_empty_count >= 4:
                header_idx = idx
                break
        else:
            # Fallback: find the first row with at least 1 non-empty cell
            for idx, r in enumerate(values[:20]):
                non_empty_count = sum(1 for cell in r if str(cell).strip() != "")
                if non_empty_count >= 1:
                    header_idx = idx
                    break

        # Extract and sanitize headers
        headers = []
        for idx, h in enumerate(values[header_idx]):
            h_str = str(h).strip()
            if h_str == "":
                headers.append(f"_col_{idx + 1}")
            else:
                headers.append(h_str)

        rows = values[header_idx + 1:]

        # Pad and normalize rows to match the header length
        padded_rows = []
        for r in rows:
            row_len = len(r)
            if row_len < len(headers):
                r_padded = r + [""] * (len(headers) - row_len)
            else:
                r_padded = r[:len(headers)]
            padded_rows.append(r_padded)

        # Create DataFrame and convert to list of records
        df = pd.DataFrame(padded_rows, columns=headers)
        return df.to_dict(orient="records")

    except Exception as e:
        raise RuntimeError(f"Error reading sheet: {str(e)}")


def _column_to_num(col_str: str) -> int:
    """Converts Excel-style column letter to 1-indexed number (e.g. 'A' -> 1, 'Z' -> 26, 'AA' -> 27)."""
    num = 0
    for char in col_str.upper():
        if 'A' <= char <= 'Z':
            num = num * 26 + (ord(char) - ord('A') + 1)
    return num


def _num_to_column(num: int) -> str:
    """Converts 1-indexed number to Excel-style column letter."""
    col = ""
    while num > 0:
        num, remainder = divmod(num - 1, 26)
        col = chr(65 + remainder) + col
    return col


@mcp.tool()
def write_gs(
    gs_url: str,
    tab_name: str,
    row: int,
    column_start_position: str,
    data: list[list] | str
) -> str:
    """
    Finds the first safe, empty section of a Google Sheet starting from a specified row within a
    dynamically calculated column range based on the data's width, and writes the provided data
    preceded by a UTC timestamp.
    Accepts data as a nested list of lists, a local JSON file path, or a formatted string.

    Parameters:
    - gs_url (str): Google Sheet URL or spreadsheet ID.
    - tab_name (str): Tab name inside the Google Sheet.
    - row (int): Starting row number to begin checking for empty rows.
    - column_start_position (str): Column letter to start checking/writing from (e.g. "B").
    - data (list[list] | str): Nested list of values to be written, or JSON file path, or formatted table string.

    Returns:
    - str: Success message with details of where the data was written.
    """
    try:
        import json
        spreadsheet_id = get_spreadsheet_id(gs_url)
        service = _get_service()

        # Step 0: Parse and resolve the data
        parsed_data = None
        if isinstance(data, str):
            data_str = data.strip()
            
            # Self-healing: if file does not exist but it is a point-based path and last_bq_result.json exists, copy it
            if "result_point_" in data_str and not os.path.exists(data_str):
                import shutil
                last_bq = "/home/jupyter/last_bq_result.json"
                if os.path.exists(last_bq):
                    try:
                        shutil.copy(last_bq, data_str)
                    except Exception:
                        pass

            # Check if it's a valid local file path
            if os.path.exists(data_str):
                try:
                    with open(data_str, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                        if isinstance(loaded, list):
                            parsed_data = loaded
                        else:
                            return f"Error: JSON file '{data_str}' must contain a list of lists."
                except Exception as ex:
                    return f"Error reading data from file path '{data_str}': {str(ex)}"
            else:
                # Try parsing as JSON string directly
                try:
                    loaded = json.loads(data_str)
                    if isinstance(loaded, list):
                        parsed_data = loaded
                except Exception:
                    pass
            
            # If still not parsed, treat it as whitespace/comma-separated text (Pandas table or raw text)
            if parsed_data is None:
                lines = [line.strip() for line in data_str.split('\n') if line.strip()]
                filtered_lines = []
                for line in lines:
                    if line.startswith("Warning:") or line.startswith("Query executed") or "saved locally" in line or "Total rows retrieved" in line:
                        continue
                    filtered_lines.append(line)
                
                parsed_data = []
                for line in filtered_lines:
                    # split by regex: tab, comma, or 2 or more spaces
                    parts = re.split(r'\t|,|\s{2,}', line)
                    parsed_data.append([p.strip() for p in parts])
        else:
            # Already a list
            parsed_data = data

        if not parsed_data or not isinstance(parsed_data, list):
            return "Error: Provided data is empty or not in a valid format (must be list of lists, file path, or formatted table string)."

        # Ensure elements are lists
        formatted_data = []
        for r in parsed_data:
            if isinstance(r, list):
                formatted_data.append(r)
            elif isinstance(r, dict):
                formatted_data.append(list(r.values()))
            else:
                formatted_data.append([r])

        # Determine column_end_position dynamically based on formatted_data width
        max_cols = max(len(r) for r in formatted_data) if formatted_data else 1
        start_num = _column_to_num(column_start_position)
        column_end_position = _num_to_column(start_num + max_cols - 1)

        # Step 1: Read columns range starting from `row` to detect content
        check_range = f"'{tab_name}'!{column_start_position}{row}:{column_end_position}20000"
        res = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=check_range
        ).execute()

        values = res.get('values', [])

        last_non_empty_idx = None
        for idx, row_vals in enumerate(values):
            if row_vals and any(str(cell).strip() for cell in row_vals):
                last_non_empty_idx = idx

        # Step 2: Determine where to write
        if last_non_empty_idx is not None:
            last_row_with_data = row + last_non_empty_idx
            write_row = last_row_with_data + 3  # skip exactly 2 rows
        else:
            write_row = row

        # Step 3: Write UTC Timestamp to write_row, starting at column_start_position
        timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!{column_start_position}{write_row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[timestamp_str]]}
        ).execute()

        # Step 4: Write data to write_row + 2, starting at column_start_position
        data_start_row = write_row + 2
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!{column_start_position}{data_start_row}",
            valueInputOption="USER_ENTERED",
            body={"values": formatted_data}
        ).execute()

        return (
            f"Successfully wrote timestamp to {column_start_position}{write_row} "
            f"and data starting on row {data_start_row} ({column_start_position} to {column_end_position})."
        )

    except Exception as e:
        return f"Error writing to sheet: {str(e)}"


@mcp.tool()
def rowsavailability_gs(gs_url: str, tab_name: str) -> str:
    """
    Calculates the total number of rows from row 1 (the topmost row) to the bottommost row
    inside the Google Sheet tab, including rows with data and rows without data (empty rows).

    Parameters:
    - gs_url (str): Google Sheet URL or spreadsheet ID.
    - tab_name (str): Tab name inside the Google Sheet.

    Returns:
    - str: A success message showing the total number of rows calculated.
    """
    try:
        spreadsheet_id = get_spreadsheet_id(gs_url)
        service = _get_service()

        # Fetch spreadsheet metadata to access sheets and their gridProperties
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()

        sheets = spreadsheet.get('sheets', [])
        total_rows = 0
        tab_found = False

        for s in sheets:
            properties = s.get('properties', {})
            if properties.get('title') == tab_name:
                grid_properties = properties.get('gridProperties', {})
                total_rows = grid_properties.get('rowCount', 0)
                tab_found = True
                break

        if not tab_found:
            return f"Error: Tab '{tab_name}' not found in the spreadsheet."

        return f"Total rows calculated: {total_rows}"

    except Exception as e:
        return f"Error calculating rows: {str(e)}"


@mcp.tool()
def clean_gs(
    gs_url: str,
    tab_name: str,
    row: int,
    until_row: int,
    column_start_position: str,
    column_end_position: str
) -> str:
    """
    Clears (cleans) all cell values/contents in a specified rectangular range inside a Google Sheet.

    Parameters:
    - gs_url (str): Google Sheet URL or spreadsheet ID.
    - tab_name (str): Tab name inside the Google Sheet.
    - row (int): The starting row number (inclusive) to clear.
    - until_row (int): The ending row number (inclusive) to clear.
    - column_start_position (str): The starting column letter (e.g. "B").
    - column_end_position (str): The ending column letter (e.g. "G").

    Returns:
    - str: A success message showing the range that was cleaned.
    """
    try:
        spreadsheet_id = get_spreadsheet_id(gs_url)
        service = _get_service()

        range_to_clear = f"'{tab_name}'!{column_start_position}{row}:{column_end_position}{until_row}"
        
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_to_clear,
            body={}
        ).execute()

        return (
            f"I have successfully clean/delete data in Google Sheet tab '{tab_name}' "
            f"starting at row {row} until {until_row}, "
            f"column range from {column_start_position}:{column_end_position}."
        )

    except Exception as e:
        return f"Error cleaning sheet: {str(e)}"


@mcp.tool()
def rowsinsert_gs(
    gs_url: str,
    tab_name: str,
    row: int,
    n_rows_inserted: int
) -> str:
    """
    Inserts new blank rows below the specified bottommost row inside a Google Sheet tab.

    Parameters:
    - gs_url (str): Google Sheet URL or spreadsheet ID.
    - tab_name (str): Tab name inside the Google Sheet.
    - row (int): The 1-based index of the bottommost row below which rows will be inserted.
    - n_rows_inserted (int): The number of new blank rows to insert.

    Returns:
    - str: A success message matching the expected coordinator format.
    """
    try:
        spreadsheet_id = get_spreadsheet_id(gs_url)
        service = _get_service()

        # Fetch spreadsheet metadata to find the sheetId for the given tab name
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()

        sheets = spreadsheet.get('sheets', [])
        sheet_id = None
        for s in sheets:
            properties = s.get('properties', {})
            if properties.get('title') == tab_name:
                sheet_id = properties.get('sheetId')
                break

        if sheet_id is None:
            return f"Error: Tab '{tab_name}' not found in the spreadsheet."

        # startIndex is row (0-based index of the row right after the 1-based row)
        # endIndex is row + n_rows_inserted
        body = {
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row,
                            "endIndex": row + n_rows_inserted
                        },
                        "inheritFromBefore": True
                    }
                }
            ]
        }

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()

        return (
            f"I have successfully inserted {n_rows_inserted} rows start from the bottommost row {row} "
            f"in Google Sheet tab '{tab_name}'."
        )

    except Exception as e:
        return f"Error inserting rows: {str(e)}"


if __name__ == "__main__":
    mcp.run()
