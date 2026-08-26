# Oudrie
Oudrie is Taskmaster, where user could put detailed steps and agent system adaptively execute to reach the user objective accurately. No more overloading skill context. The first use case here is BigQuery and Google Sheet task operation and completion. Especially BigQuery, not all roles in a organization have access to BigQuery. So through Oudrie, all user roles are able to analyze BigQuery tables then gain insight through Google Sheet autonomous operations. User also able to automate repetitive Google Sheet operations through Oudrie. 

## Simple Testing Instruction
1. Open this Google Sheet [Census 2012 US Agriculture](https://docs.google.com/spreadsheets/d/1lmGAV-5JFeEzWy-nZ3o3SEZF49plo8bFPHUSbg_MnBc/edit?gid=1971765118#gid=1971765118).
2. Think of repetitive task that involving many operations in Google Sheet. Or tasks that always requiring data analyst to pull data from BigQuery which you don't have access to. Then build it into multi-steps. There are example 7 tasks in this [tab "Tasks"](https://docs.google.com/spreadsheets/d/1lmGAV-5JFeEzWy-nZ3o3SEZF49plo8bFPHUSbg_MnBc/edit?gid=1971765118#gid=1971765118&range=B2:B8). If you don't know the repetitive Google Sheet-BigQuery task at the moment, it's fine, then just simply use those 7 tasks to be executed.
3. Open [Google Cloud Workbench](https://console.cloud.google.com/agent-platform/workbench/instances?project=kzxy-11239) then in one instance name "taskmaster-ignatiusandri" click "Open JupyterLab".
4. In the Launcher menu, click Terminal.
5. Paste this syntax into Terminal, then press Enter :
gemini -p "run run_tasks  
task_list_gs_url = https://docs.google.com/spreadsheets/d/1lmGAV-5JFeEzWy-nZ3o3SEZF49plo8bFPHUSbg_MnBc/, 
task_list_gs_tab = 'Tasks', 
archive_task_gs_url = https://docs.google.com/spreadsheets/d/1lmGAV-5JFeEzWy-nZ3o3SEZF49plo8bFPHUSbg_MnBc/, 
archive_task_gs_tab = 'Archive Tasks'." --yolo
The syntax explanation : task_list arguments are to inform the automation on which Google Sheet and tab containing the task list. archive_task arguments are to inform the automation which Google Sheet and tab to store completed approved tasks list, including Closing Timestamp. yolo is to instruct "don't wait for user review, just run run_task continuously until the end". So the automation behaves like automation, not chatting asking user for reviewing/approvals in the middle.
6. Oudrie will execute task one-by-one from task 001, until task 007. After task 007 finished, the automation stops. In tab "Tasks", column "Vertex AI Log" is filled by Oudrie to explain the handoffs, column "Update Timestamp" is filled when the task is finished. Then the automation stop.
7. User check [tab "Result"](https://docs.google.com/spreadsheets/d/1lmGAV-5JFeEzWy-nZ3o3SEZF49plo8bFPHUSbg_MnBc/edit?gid=750890070#gid=750890070). That is where Oudrie delivers the tasks' results.
8. For the good tasks, user write Yes in column "Approved (Yes/No)". But for the less good tasks needing rework, in tab "Tasks" don't hesitate to write No in column "Approved (Yes/No)" and put the feedback how Oudrie should improve in column "Feedback". For feedback, no need to write in multi-step details. Alternatively user could edit the steps in column "Task List" , perhaps there was typo in table name/wrong result location etc., then in column "Feedback" just write "Please re-run the task.".
9. User paste the exact same syntax on point 5 into Terminal, then press Enter.
10. After automation stop, user review again the tasks. If necessary, repeat the step 8-10, until all tasks are approved Yes.
11. After all tasks are approved Yes, user paste again the exact same syntax on point 5 into Terminal. Then press Enter.
12. Oudrie will copy all approved tasks lists from tab "Tasks" into [tab "Archive Tasks"](https://docs.google.com/spreadsheets/d/1lmGAV-5JFeEzWy-nZ3o3SEZF49plo8bFPHUSbg_MnBc/edit?gid=1148560669#gid=1148560669). Plus adding Closing Timestamp to indicate when the task are officially closed. Then on tab "Tasks", Oudrie will clean up contents on column "Vertex AI Log", "Update Timestamp", and "Approved (Yes/No)". Then the automation stop.
13. When user paste the exact same syntax on point 5 into Terminal and then press Enter, automation will run again from point 6.
 
