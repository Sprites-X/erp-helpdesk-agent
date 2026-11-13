@echo off
rem Per-stage latency + qwen2.5:7b vs qwen2.5:3b on all 3 eval sets
rem Output: latency_log.txt here, copies of the reports in results\latency\
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set COLUMNS=150
set PY=.venv\Scripts\python.exe
set LOG=%~dp0latency_log.txt
echo START %date% %time% > "%LOG%"
if not exist %PY% (echo RESULT NO_VENV - run run_test.bat first >> "%LOG%" & goto end)

echo ==== GPU >> "%LOG%"
nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv >> "%LOG%" 2>&1
ollama --version >> "%LOG%" 2>&1

echo ==== PULL qwen2.5:3b >> "%LOG%"
ollama pull qwen2.5:3b > pull_log.txt 2>&1
if errorlevel 1 (echo RESULT PULL_FAILED - see pull_log.txt >> "%LOG%" & goto end)
ollama list >> "%LOG%" 2>&1

echo ==== PROBE connection overhead >> "%LOG%"
%PY% tools\probe_ollama.py >> "%LOG%" 2>&1

echo ==== UNIT TESTS >> "%LOG%"
%PY% -m pip install -q -r requirements-dev.txt >> "%LOG%" 2>&1
%PY% -m pytest -q >> "%LOG%" 2>&1

echo ==== PREP >> "%LOG%"
set COLUMNS=140
%PY% prep.py --save-html docs\prep.html >> "%LOG%" 2>&1
if errorlevel 1 (echo RESULT PREP_FAILED >> "%LOG%" & goto end)
set COLUMNS=150

call :model 7b
call :model 3b

echo ==== DEMO 7b >> "%LOG%"
set CHAT_MODEL=qwen2.5:7b
set COLUMNS=110
%PY% chat.py --demo --no-pause --save-html docs\demo.html >> "%LOG%" 2>&1
echo ==== OLLAMA_PS demo >> "%LOG%"
ollama ps >> "%LOG%" 2>&1

echo ==== COMPARE >> "%LOG%"
%PY% tools\compare_reports.py 7b 3b >> "%LOG%" 2>&1

if not exist results\latency mkdir results\latency
copy /y outputs\eval_report*_7b.json results\latency\ >> "%LOG%" 2>&1
copy /y outputs\eval_report*_3b.json results\latency\ >> "%LOG%" 2>&1
copy /y "%LOG%" results\latency\latency_log.txt >nul 2>&1
echo RESULT DONE >> "%LOG%"
goto end

:model
echo ==== MODEL qwen2.5:%1 >> "%LOG%"
set CHAT_MODEL=qwen2.5:%1
%PY% eval.py --tag %1 >> "%LOG%" 2>&1
%PY% eval.py --file data\eval\heldout.jsonl --tag %1 >> "%LOG%" 2>&1
%PY% eval.py --file data\eval\final_check.jsonl --tag %1 >> "%LOG%" 2>&1
echo ==== OLLAMA_PS %1 >> "%LOG%"
ollama ps >> "%LOG%" 2>&1
ollama stop qwen2.5:%1 >> "%LOG%" 2>&1
exit /b

:end
echo END %date% %time% >> "%LOG%"
copy /y "%LOG%" results\latency\latency_log.txt >nul 2>&1
