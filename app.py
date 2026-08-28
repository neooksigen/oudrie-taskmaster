import asyncio
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Pipeline Runner Web UI")

# Ensure templates directory exists and index.html is readable
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse(
            content="<h1>Error: templates/index.html not found.</h1>", 
            status_code=500
        )
    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/run")
async def run_pipeline(
    task_list_gs_url: str = "",
    task_list_gs_tab: str = "",
    archive_task_gs_url: str = "",
    archive_task_gs_tab: str = ""
):
    async def log_stream():
        # Prepare the execution command
        cmd = ["python3", "run_tasks.py"]
        
        # Only append arguments if they are explicitly provided by the user,
        # otherwise run_tasks.py will fall back to its internal defaults.
        if task_list_gs_url.strip():
            cmd.append(f"task_list_gs_url={task_list_gs_url.strip()}")
        if task_list_gs_tab.strip():
            cmd.append(f"task_list_gs_tab={task_list_gs_tab.strip()}")
        if archive_task_gs_url.strip():
            cmd.append(f"archive_task_gs_url={archive_task_gs_url.strip()}")
        if archive_task_gs_tab.strip():
            cmd.append(f"archive_task_gs_tab={archive_task_gs_tab.strip()}")

        yield f"data: [INFO] Spawning pipeline process: {' '.join(cmd)}\n\n"
        await asyncio.sleep(0.1)

        try:
            # Execute run_tasks.py as a subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            # Read stdout/stderr line-by-line and yield via SSE.
            # Use asyncio.wait_for to send periodic heartbeats if the process is silent,
            # which prevents Google Front End (GFE) or proxies from dropping the connection as idle.
            while True:
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=15.0)
                    if not line:
                        break
                    decoded_line = line.decode('utf-8', errors='replace').rstrip('\r\n')
                    yield f"data: {decoded_line}\n\n"
                except asyncio.TimeoutError:
                    # SSE Comment (ignored by clients but keeps connection active)
                    yield ": keep-alive\n\n"
            
            # Wait for process termination
            await process.wait()
            yield f"data: \n\n"
            yield f"data: [SUCCESS] Pipeline execution finished with exit code {process.returncode}\n\n"
            
        except Exception as e:
            yield f"data: [ERROR] Failed to execute pipeline: {str(e)}\n\n"
        finally:
            # AUTOMATIC CLEANUP: If the user disconnects or closes the tab,
            # terminate the active pipeline subprocess immediately.
            if 'process' in locals() and process.returncode is None:
                try:
                    process.terminate()
                    await process.wait()
                except Exception:
                    pass

    return StreamingResponse(log_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    # Listen on all interfaces, default port 8080 (Cloud Run expectation)
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
