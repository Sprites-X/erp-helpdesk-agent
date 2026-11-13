@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe tools\experiment.py data\eval\questions.jsonl data\eval\heldout.jsonl data\eval\final_check.jsonl > experiment_stdout.txt 2>&1
echo END >> experiment_stdout.txt
