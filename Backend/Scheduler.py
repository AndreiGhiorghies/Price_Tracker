import subprocess
import sys
import json
import os

from Database import SCRIPT_DIR, CONFIG_PATH

def run_cmd(args):
    try:
        cp = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("'schtasks' was not found. Must be run on Windows.")
    
    return cp.returncode, cp.stdout.strip(), cp.stderr.strip()

def task_exists(task_name: str) -> bool:
    args = ["schtasks", "/Query", "/TN", task_name]
    rc, _, _ = run_cmd(args)

    return rc == 0

def create_task(run_time: str,
                scrape_query: str,
                task_name: str = "Price_tracker",
                script_path: str = SCRIPT_DIR + "\\SchedulerStarter.py"
):

    if task_exists(task_name):
        print(f"[warn] Task '{task_name}' already exists.")
        return False
    
    with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
    
    config["schedule_query"] = scrape_query
    config["schedule_time"] = run_time

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    python_exe = sys.executable.replace("python.exe", "pythonw.exe")
    tr = f'"{python_exe}" "{script_path}"'
    args = ["schtasks", "/Create", "/TN", task_name, "/TR", tr, "/ST", run_time, "/SC", "DAILY"]

    rc, out, err = run_cmd(args)
    if rc == 0:
        subprocess.run([
            "powershell", "-Command",
            r'$task = Get-ScheduledTask -TaskName "Price_tracker"; '
            r'$task.Settings.DisallowStartIfOnBatteries = $false; '
            r'$task.Settings.StopIfGoingOnBatteries = $false; '
            r'$task.Settings.StartWhenAvailable = $true; '
            r'Set-ScheduledTask -TaskName "Price_tracker" -Settings $task.Settings'
        ])

        return True
    else:
        print(f"[err] Task creation failed (code {rc}).")
        if out:
            print("stdout:", out)
        if err:
            print("stderr:", err)
        
        return False

def delete_task(task_name: str = "Price_tracker") -> bool:
    if not task_exists(task_name):
        return False

    args = ["schtasks", "/Delete", "/TN", task_name, "/F"]
    rc, out, err = run_cmd(args)

    if rc == 0:
        return True
    else:
        print(f"[err] Task deletion failed (code {rc}).")
        if out:
            print("stdout:", out)
        if err:
            print("stderr:", err)
        
        return False
