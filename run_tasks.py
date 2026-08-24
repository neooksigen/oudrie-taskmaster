#!/usr/bin/env python3
"""
run_tasks.py

Executes the automated task pipeline.
Coordinates task execution across BigQuery and Google Sheets using the
agent_coordinator defined in agent_system.py.

Usage:
  1. Trigger Task Pipeline:
     python3 run_tasks.py task_list_gs_url = <url>, task_list_gs_tab = 'Tasks', ...
  2. Trigger Conversational Chat:
     python3 run_tasks.py
"""

import os
import sys
import re
import datetime
import asyncio
import gspread

# Add workspace path to support imports if executed from sibling folders
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from agent_system import agent_coordinator


# ==============================================================================
# Helper to extract text from Event content
# ==============================================================================
def extract_text_from_event_content(content) -> str:
    """Safely extracts a raw text string from any ADK Event content object."""
    if isinstance(content, str):
        return content
    if hasattr(content, "parts") and content.parts:
        text_parts = []
        for part in content.parts:
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
        return "\n".join(text_parts)
    if hasattr(content, "text") and content.text:
        return content.text
    return str(content)


# ==============================================================================
# Dynamic Column Mapping Helper
# ==============================================================================
def col_num_to_letter(col_num: int) -> str:
    """Converts a 1-indexed column number to Excel column letter (e.g. 1 -> A, 27 -> AA)."""
    string = ""
    while col_num > 0:
        col_num, remainder = divmod(col_num - 1, 26)
        string = chr(65 + remainder) + string
    return string


# ==============================================================================
# CLI Argument Parser Helper
# ==============================================================================
def parse_pipeline_arguments(args: list[str]) -> dict:
    """Parses custom 'parameter = value' styles from CLI args with a robust regex."""
    params = {
        "task_list_gs_url": "https://docs.google.com/spreadsheets/d/1zHxFegRSy24RpIPCx6f_BPVHWIrSJeilY_4I4LBgV2Q/",
        "task_list_gs_tab": "Tasks",
        "archive_task_gs_url": "https://docs.google.com/spreadsheets/d/1zHxFegRSy24RpIPCx6f_BPVHWIrSJeilY_4I4LBgV2Q/",
        "archive_task_gs_tab": "Archive Tasks"
    }

    full_args_str = " ".join(args)
    # Regex captures: key = 'value' or key = "value" or key = value
    pattern = r'([a-zA-Z0-9_]+)\s*=\s*(?:\'([^\']*)\'|"([^"]*)"|([^\s,]+))'
    matches = re.findall(pattern, full_args_str)

    for key, q1, q2, unq in matches:
        val = q1 or q2 or unq
        if val:
            # Clean up trailing comma, period, or quotes
            val = val.strip().strip(",").strip(".")
            # Support both _trix_ and _gs_ parameter styles
            normalized_key = key.replace("_trix_", "_gs_")
            if normalized_key in params:
                params[normalized_key] = val

    return params


# ==============================================================================
# Single-Turn Agent Executer
# ==============================================================================
async def run_coordinator_agent(prompt: str) -> str:
    """Runs a single workflow query on the agent_coordinator and returns its summary response."""
    app_name = "task_master"
    user_id = "pipeline_runner_system"
    session_id = f"session_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    session_service = InMemorySessionService()

    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id
    )

    runner = Runner(
        agent=agent_coordinator,
        app_name=app_name,
        session_service=session_service
    )

    formatted_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)]
    )

    coordinator_responses = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=formatted_message
    ):
        author = getattr(event, "author", "System")
        content = getattr(event, "content", event)

        # Print the stream to console in real-time
        print(f"[{author}]: {content}")

        if author == "agent_coordinator":
            txt = extract_text_from_event_content(content)
            # Exclude inner orchestration function calls/signatures from summary text
            if txt and not ("transfer_to_agent" in txt or "FunctionCall" in txt or "list_skills" in txt):
                coordinator_responses.append(txt)

    return "\n".join(coordinator_responses).strip()


# ==============================================================================
# Task List Pipeline Runner
# ==============================================================================
async def run_pipeline(args: list[str]):
    """Main automated task pipeline execution engine."""
    params = parse_pipeline_arguments(args)

    print("==========================================================")
    print("STARTING TASK EXECUTION PIPELINE")
    print("==========================================================")
    print(f"Task List URL : {params['task_list_gs_url']}")
    print(f"Task List Tab : {params['task_list_gs_tab']}")
    print(f"Archive URL   : {params['archive_task_gs_url']}")
    print(f"Archive Tab   : {params['archive_task_gs_tab']}")
    print("==========================================================\n")

    # 1. Authenticate with kzxy_credentials.json
    creds_file = "/home/jupyter/kzxy_credentials.json"
    if not os.path.exists(creds_file):
        print(f"Error: Credentials file not found at {creds_file}")
        return

    try:
        gc = gspread.service_account(filename=creds_file)
        task_workbook = gc.open_by_url(params["task_list_gs_url"])
        task_sheet = task_workbook.worksheet(params["task_list_gs_tab"])
    except Exception as e:
        print(f"Failed to authenticate or open task spreadsheet: {e}")
        return

    # 2. Retrieve Headers and Build Dynamic Column Mapping
    try:
        headers = [str(h).strip() for h in task_sheet.row_values(1)]
    except Exception as e:
        print(f"Error reading row values from sheet: {e}")
        return

    col_map = {h: idx + 1 for idx, h in enumerate(headers)}
    required_cols = [
        "No",
        "Task List (Prompt List)",
        "Update Timestamp",
        "Approved (Yes/No)",
        "Feedback",
        "Loop Order"
    ]

    for col in required_cols:
        if col not in col_map:
            print(f"Error: Expected required column '{col}' is missing. Found columns: {headers}")
            return

    # Helper function to write to cells using mapped headers
    def write_cell(row_index, header_name, value):
        col_idx = col_map[header_name]
        col_letter = col_num_to_letter(col_idx)
        task_sheet.update(range_name=f"{col_letter}{row_index}", values=[[value]], value_input_option="USER_ENTERED")

    # 3. Read All Rows
    records = task_sheet.get_all_records()
    if not records:
        print("No tasks found inside the specified sheet tab.")
        return

    # Helper to safely normalize and compare strings
    def get_normalized(val) -> str:
        return str(val).strip().lower()

    # 4. Count and analyze statuses in column "Approved (Yes/No)"
    total_tasks = len(records)
    blank_count = 0
    yes_count = 0
    no_count = 0
    ut_blank_count = 0
    ut_filled_count = 0

    for row in records:
        app_val = get_normalized(row.get("Approved (Yes/No)", ""))
        if app_val == "":
            blank_count += 1
        elif app_val == "yes":
            yes_count += 1
        elif app_val == "no":
            no_count += 1
        else:
            # Treat other unrecognized values as blank (incomplete review)
            blank_count += 1

        update_timestamp_val = get_normalized(row.get("Update Timestamp"))
        if update_timestamp_val == "":
            ut_blank_count += 1 
        else:
            ut_filled_count += 1
            

    print(f"Current State: Total Tasks={total_tasks}, Approved(Yes)={yes_count}, Rejected(No)={no_count}, Blank/Pending={blank_count}\n")

    # =====================================================================================================
    # FLOW 1: All tasks have update timestamp, but no one has approval status (=not reviewed by user at all)
    # =====================================================================================================
    if (ut_filled_count == total_tasks) and (blank_count == total_tasks) :
        print("\n[BLOCKED] Pipeline execution aborted.")
        print("Please complete the approval status (Yes/No) for all tasks completely,")
        print("and provide feedback in the 'Feedback' column for any tasks you do not approve.")
        print("Then run the pipeline again. Stopping pipeline.")
        return


    # ==========================================================================
    # FLOW 2: All tasks have not run at all, no content at all in "Approved (Yes/No)"
    # ==========================================================================
    elif ut_filled_count == 0 and (blank_count == total_tasks):
        print("All tasks have no approval status. Initiating full sequential run from task 001...")
        
        for idx, row in enumerate(records):
            row_num = idx + 2  # 1-indexed, skipping header
            task_no = row.get("No")
            task_text = str(row.get("Task List (Prompt List)", "")).strip()

            print("-" * 60)
            print(f"Executing Task {task_no}: '{task_text[:60]}...'")

            # Execute the task via Agent Coordinator
            summary_result = await run_coordinator_agent(task_text)

            # Update the Update Timestamp and Vertex AI Log columns
            current_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"Writing Vertex AI Log and update timestamp to row {row_num}...")
            write_cell(row_num, "Vertex AI Log", summary_result)
            write_cell(row_num, "Update Timestamp", current_time)

        print("\nAll tasks in the list have been executed. Stopping pipeline.")
        return

    # ==========================================================================
    # FLOW 3: All tasks have content "Yes"
    # ==========================================================================
    elif yes_count == total_tasks:
        print("All tasks are Approved ('Yes')! Copying tasks to archive tab...")
        try:
            archive_workbook = gc.open_by_url(params["archive_task_gs_url"])
            archive_sheet = archive_workbook.worksheet(params["archive_task_gs_tab"])
        except Exception as e:
            print(f"Failed to open archive spreadsheet/tab: {e}")
            return

        # Find the absolute first empty row of the archive sheet
        archive_all_values = archive_sheet.get_all_values()
        last_archive_row = 0
        for i, row in enumerate(archive_all_values):
            if any(str(cell).strip() for cell in row):
                last_archive_row = i + 1

        archive_start_row = last_archive_row + 1 if last_archive_row > 0 else 1

        # Setup headers if the archive tab is completely empty
        if last_archive_row == 0:
            archive_headers = [
                "Task List (Prompt List)",
                "Vertex AI Log",
                "Update Timestamp",
                "Closing Timestamp"
            ]
            archive_sheet.update(
                range_name="A1",
                values=[archive_headers],
                value_input_option="USER_ENTERED"
            )
            archive_start_row = 2
            archive_headers_list = archive_headers
        else:
            archive_headers_list = [str(h).strip() for h in archive_all_values[0]]

        arc_col_map = {h: idx + 1 for idx, h in enumerate(archive_headers_list)}
        
        # Verify archive required headers are present
        arc_required = ["Task List (Prompt List)", "Vertex AI Log", "Update Timestamp", "Closing Timestamp"]
        for col in arc_required:
            if col not in arc_col_map:
                print(f"Error: Archive tab is missing required column '{col}'. Available columns: {archive_headers_list}")
                return

        # Prepare bulk rows to write to archive tab
        utc_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        archive_rows = []
        for row in records:
            new_row = [""] * len(archive_headers_list)
            new_row[arc_col_map["Task List (Prompt List)"] - 1] = row.get("Task List (Prompt List)", "")
            new_row[arc_col_map["Vertex AI Log"] - 1] = row.get("Vertex AI Log", "")            
            new_row[arc_col_map["Update Timestamp"] - 1] = row.get("Update Timestamp", "")
            new_row[arc_col_map["Closing Timestamp"] - 1] = utc_now
            archive_rows.append(new_row)

        # Write to first empty section in bulk
        write_range = f"A{archive_start_row}"
        archive_sheet.update(range_name=write_range, values=archive_rows, value_input_option="USER_ENTERED")
        print(f"Successfully archived {len(archive_rows)} tasks into '{params['archive_task_gs_tab']}' starting at row {archive_start_row}.")
        print("Pipeline execution completed successfully.")
        return

    # ==========================================================================
    # FLOW 4: Some tasks have "Yes" (and some are blank, making the review incomplete)
    # ==========================================================================
    elif blank_count > 0 and (yes_count > 0 or no_count > 0):
        print("\n[BLOCKED] Pipeline execution aborted.")
        print("Please complete the approval status (Yes/No) for all tasks completely,")
        print("and provide feedback in the 'Feedback' column for any tasks you do not approve.")
        print("Then run the pipeline again. Stopping pipeline.")
        return

    # ==========================================================================
    # FLOW 5: Some tasks have content "No" (and all tasks are completely reviewed)
    # ==========================================================================
    elif no_count > 0:
        # Validate that every rejected task ("No") has some feedback content
        any_blank_feedback = False
        for row in records:
            app_val = get_normalized(row.get("Approved (Yes/No)", ""))
            if app_val == "no":
                fb_text = str(row.get("Feedback", "")).strip()
                if not fb_text:
                    any_blank_feedback = True
                    break

        if any_blank_feedback:
            print("\n[BLOCKED] Pipeline execution aborted.")
            print("Please put feedback in the 'Feedback' column for all rejected tasks and run the pipeline again. Stopping pipeline.")
            return

        print("Executing rejected tasks sequentially...")
        for idx, row in enumerate(records):
            row_num = idx + 2
            app_val = get_normalized(row.get("Approved (Yes/No)", ""))

            if app_val == "no":
                task_no = row.get("No")
                task_text = str(row.get("Task List (Prompt List)", "")).strip()
                feedback_text = str(row.get("Feedback", "")).strip()

                print("-" * 60)
                print(f"Re-running Task {task_no} with Feedback: '{feedback_text[:60]}...'")

                revision_prompt = (
                    f"Please execute this task: '{task_text}'. \n\n"
                    f"IMPORTANT FEEDBACK: Your previous attempt was rejected with this feedback: '{feedback_text}'. "
                    f"Please adjust your approach based on this feedback and deliver the updated result."
                )

                # Re-execute task via Agent Coordinator
                summary_result = await run_coordinator_agent(revision_prompt)

                current_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

                # Update spreadsheet: update timestamp, clear Approved mark and Feedback
                print("Writing Vertex AI Log, update timestamp, and resetting approval/feedback marks...")
                write_cell(row_num, "Vertex AI Log", summary_result)
                write_cell(row_num, "Update Timestamp", current_time)
                write_cell(row_num, "Approved (Yes/No)", "")
                write_cell(row_num, "Feedback", "")

        print("\nAll rejected tasks have been completed and updated. Stopping pipeline.")
        return

        
    else:
        print("No eligible tasks to process or unrecognized state. Stopping pipeline.")
        return


# ==============================================================================
# Conversational / Interactive Loop
# ==============================================================================
async def run_interactive_loop():
    """Launches an interactive, conversational loop inside the terminal with the Agent Coordinator."""
    app_name = "task_master_app"
    user_id = "interactive_user"
    session_id = "interactive_session"
    session_service = InMemorySessionService()

    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id
    )

    runner = Runner(
        agent=agent_coordinator,
        app_name=app_name,
        session_service=session_service
    )

    print("=======================================================================")
    print("Task Master Chat Online! (Type 'exit' or 'quit' to exit)")
    print("=======================================================================")

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit"]:
                print("Exiting chat. Goodbye!")
                break
        except (KeyboardInterrupt, EOFError):
            print("\nExiting chat. Goodbye!")
            break

        print("\n--- Event Stream ---")
        formatted_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_input)]
        )

        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=formatted_message
            ):
                author = getattr(event, "author", "System")
                content = getattr(event, "content", event)
                print(f"[{author}]: {content}")
        except Exception as e:
            print(f"\n[Error executing step]: {e}")


# ==============================================================================
# Entry Point Routing
# ==============================================================================
def main():
    args = sys.argv[1:]
    # If the user passes any arguments that look like parameters, trigger the pipeline.
    # Otherwise, launch the interactive chat loop.
    has_params = any("=" in arg for arg in args)

    if has_params:
        asyncio.run(run_pipeline(args))
    else:
        asyncio.run(run_interactive_loop())


if __name__ == "__main__":
    main()
