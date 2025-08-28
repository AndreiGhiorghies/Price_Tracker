#!/usr/bin/env python3
"""
tasks_manager.py

Funcționalități:
 - create_task(...)  -> creează un task în Task Scheduler și salvează metadata în tasks.json
 - delete_task(...)  -> șterge un task din Task Scheduler și (opțional) din tasks.json
 - task_exists(...)  -> verifică existența task-ului
 - load/save JSON metadata la path './tasks.json' (configurabil)

Exemple:
  from tasks_manager import create_task, delete_task

  create_task("MyTask", r"C:\\scripts\\my.py", "15:30", daily=True) 
  delete_task("MyTask")
"""
import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import os

METADATA_FILE = Path("tasks.json")

def run_cmd(args):
    """Run subprocess and return (returncode, stdout, stderr)."""
    try:
        cp = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("'schtasks' nu a fost găsit. Rulează pe Windows.")
    return cp.returncode, cp.stdout.strip(), cp.stderr.strip()

def task_exists(task_name: str) -> bool:
    """Returnează True dacă un task cu numele dat există."""
    args = ["schtasks", "/Query", "/TN", task_name]
    rc, out, err = run_cmd(args)
    # schtasks /Query returnează 0 dacă găsește taskul
    return rc == 0

def create_task(run_time: str,
                scrape_query: str,
                task_name: str = "Price_tracker",
                script_path: str = os.path.dirname(os.path.abspath(__file__)) + "\\SchedulerStarter.py"
):

    if task_exists(task_name):
        print(f"[warn] Task '{task_name}' există deja.")
        return False
    
    with open("D:\\Python\\Web_Scraper\\config.json", "r") as f:
            config = json.load(f)
    config["schedule_query"] = scrape_query
    config["schedule_time"] = run_time

    with open("D:\\Python\\Web_Scraper\\config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    python_exe = sys.executable.replace("python.exe", "pythonw.exe")
    tr = f'"{python_exe}" "{script_path}"'
    args = ["schtasks", "/Create", "/TN", task_name, "/TR", tr, "/ST", run_time, "/SC", "DAILY"]

    print("Execut comanda:", " ".join(args))
    rc, out, err = run_cmd(args)
    if rc == 0:
        print(f"[ok] Task '{task_name}' creat cu succes.")
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
        print(f"[err] Creare task eșuată (code {rc}).")
        if out:
            print("stdout:", out)
        if err:
            print("stderr:", err)
        return False

def delete_task(task_name: str = "Price_tracker") -> bool:
    if not task_exists(task_name):
        print(f"[warn] Task '{task_name}' nu pare să existe.")
        return False

    args = ["schtasks", "/Delete", "/TN", task_name, "/F"]
    print("Execut comanda:", " ".join(args))
    rc, out, err = run_cmd(args)
    if rc == 0:
        print(f"[ok] Task '{task_name}' șters cu succes.")
        return True
    else:
        print(f"[err] Ștergere task eșuată (code {rc}).")
        if out:
            print("stdout:", out)
        if err:
            print("stderr:", err)
        return False

if __name__ == "__main__":
    ok = delete_task("Price_tracker")
    ok = create_task(
        task_name="Price_tracker",
        script_path= os.path.dirname(os.path.abspath(__file__)) + "\\SchedulerStarter.py",
        run_time="20:37",
        scrape_query="Telefon samsung a55"
    )
