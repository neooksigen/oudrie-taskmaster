#!/usr/bin/env python3
"""
agent_system.py

An enterprise-grade multi-agent orchestrator system built on the Google Agent Development Kit (ADK).
Integrates three specialized agents with loaded markdown skills:
- agent_coordinator: Translates user requests into sequential to-do plans and delegates tasks.
- bq_v2_agent: Executes and refines BigQuery queries to check GPG data quality.
- trix_v2_agent: Reads, analyzes, and writes datasets in Google Sheets/Trix.
"""

import os
import sys
import asyncio
import dotenv
from dotenv import load_dotenv

# 1. Load Environment Variables (e.g. API keys, GCP credentials)
load_dotenv()

# Force Google GenAI SDK to use 'global' location as gemini-3.6-flash is hosted there on Vertex AI
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

try:
    from google.adk.agents.llm_agent import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from google.adk.tools import FunctionTool
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools import skill_toolset
except ImportError as e:
    print(f"Error: Missing required Google ADK library components. {e}")
    sys.exit(1)

# Import the functional tools defined in the local workspace
try:
    from bigquery_tools import code_bq
    from googlesheet_tools import read_gs, write_gs, rowsavailability_gs, clean_gs, rowsinsert_gs
except ImportError as e:
    print(f"Warning: Local workspace tool files could not be imported. Ensure bigquery_tools.py and googlesheet_tools.py are present. {e}")

# ==============================================================================
# Helper to read skills from markdown
# ==============================================================================
def load_instruction_from_skill(skill_path: str) -> str:
    """Reads the SKILL.md file to serve as the system instruction of the Agent."""
    skill_file = os.path.join(skill_path, "SKILL.md")
    if os.path.exists(skill_file):
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"Error reading skill from {skill_file}: {e}")
    return ""

# ==============================================================================
# Define ADK Function Tools
# ==============================================================================
code_bq_tool = FunctionTool(func=code_bq)
read_gs_tool = FunctionTool(func=read_gs)
write_gs_tool = FunctionTool(func=write_gs)
rowsavailability_gs_tool = FunctionTool(func=rowsavailability_gs)
clean_gs_tool = FunctionTool(func=clean_gs)
rowsinsert_gs_tool = FunctionTool(func=rowsinsert_gs)

# ==============================================================================
# Load Skills and Build Skill Toolsets
# ==============================================================================
SKILLS_DIR = "./skills"

# Load bigquery skill
bigquery_skill_path = os.path.join(SKILLS_DIR, "bigquery")
bigquery_skill = load_skill_from_dir(bigquery_skill_path)
bigquery_skills = skill_toolset.SkillToolset(skills=[bigquery_skill])
bigquery_instruction = load_instruction_from_skill(bigquery_skill_path)

# Load googlesheet skill
googlesheet_skill_path = os.path.join(SKILLS_DIR, "googlesheet")
googlesheet_skill = load_skill_from_dir(googlesheet_skill_path)
googlesheet_skills = skill_toolset.SkillToolset(skills=[googlesheet_skill])
googlesheet_instruction = load_instruction_from_skill(googlesheet_skill_path)

# Load datasource-knowledge skill
datasource_knowledge_skill_path = os.path.join(SKILLS_DIR, "datasource-knowledge")
datasource_knowledge_skill = load_skill_from_dir(datasource_knowledge_skill_path)
datasource_knowledge_skills = skill_toolset.SkillToolset(skills=[datasource_knowledge_skill])
datasource_knowledge_instruction = load_instruction_from_skill(datasource_knowledge_skill_path)

# Load agent-coordination skill
coordination_skill_path = os.path.join(SKILLS_DIR, "agent-coordination")
coordination_skill = load_skill_from_dir(coordination_skill_path)
coordination_skills = skill_toolset.SkillToolset(skills=[coordination_skill, datasource_knowledge_skill])
coordination_instruction = load_instruction_from_skill(coordination_skill_path)

# ==============================================================================
# Define Local Code Execution Tool
# ==============================================================================
def run_code(code: str) -> str:
    """
    Executes Python code locally. Use this tool for in-memory data processing,
    comparison (e.g. comparing columns with suffix _raw vs _processed), filtering,
    or other calculations. Always ensure you write results to a JSON file if required.

    Parameters:
    - code (str): The Python code block to execute.

    Returns:
    - str: The stdout and stderr output of the executed code.
    """
    import sys
    import io
    import traceback
    import pandas as pd
    import numpy as np
    import json
    import re
    import os

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()

    try:
        globals_dict = {
            "pd": pd,
            "np": np,
            "json": json,
            "re": re,
            "os": os,
        }
        exec(code, globals_dict)
        stdout_val = sys.stdout.getvalue()
        stderr_val = sys.stderr.getvalue()
        return stdout_val + stderr_val
    except Exception as e:
        return f"Error executing Python code: {str(e)}\n\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

run_code_tool = FunctionTool(func=run_code)


# ==============================================================================
# Instantiate Specialized Sub-Agents
# ==============================================================================
bigquery_agent = Agent(
    name="bigquery_agent",
    model="gemini-3.6-flash",
    instruction=bigquery_instruction,
    tools=[code_bq_tool, bigquery_skills, run_code_tool]
)

googlesheet_agent = Agent(
    name="googlesheet_agent",
    model="gemini-3.6-flash",
    instruction=googlesheet_instruction,
    tools=[
        read_gs_tool,
        write_gs_tool,
        rowsavailability_gs_tool,
        clean_gs_tool,
        rowsinsert_gs_tool,
        googlesheet_skills,
        run_code_tool
    ]
)


# ==============================================================================
# Instantiate Agent Coordinator
# ==============================================================================
agent_coordinator_instruction = coordination_instruction + "\n\n" + datasource_knowledge_instruction

agent_coordinator = Agent(
    name="agent_coordinator",
    model="gemini-3.6-flash",
    instruction=agent_coordinator_instruction,
    tools=[coordination_skills, run_code_tool],
    sub_agents=[bigquery_agent, googlesheet_agent]
)

