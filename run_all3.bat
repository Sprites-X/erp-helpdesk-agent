@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set COLUMNS=150
echo START %date% %time% > all3_log.txt
echo ==== SET 1 TUNING >> all3_log.txt
.venv\Scripts\python.exe eval.py >> all3_log.txt 2>&1
echo ==== SET 2 HELDOUT >> all3_log.txt
.venv\Scripts\python.exe eval.py --file data\eval\heldout.jsonl >> all3_log.txt 2>&1
echo ==== SET 3 FINAL_CHECK >> all3_log.txt
.venv\Scripts\python.exe eval.py --file data\eval\final_check.jsonl >> all3_log.txt 2>&1
echo END %date% %time% >> all3_log.txt
