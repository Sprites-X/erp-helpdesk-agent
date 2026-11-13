@echo off
rem Evidence rule experiment: STRICT_EVIDENCE=0 (old) vs 1 (chunk headers and FAQ question lines are not evidence)
rem Output: evidence_log.txt here, copies of the reports in results\evidence\
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set COLUMNS=150
set PY=.venv\Scripts\python.exe
set LOG=%~dp0evidence_log.txt
echo START %date% %time% > "%LOG%"
echo ==== UNIT TESTS >> "%LOG%"
%PY% -m pytest -q -p no:cacheprovider >> "%LOG%" 2>&1
echo ==== PROBE >> "%LOG%"
%PY% tools\probe_ollama.py >> "%LOG%" 2>&1

call :run 0
call :run 1

echo ==== COMPARE >> "%LOG%"
%PY% tools\compare_reports.py ev0 ev1 >> "%LOG%" 2>&1

echo ==== DEMO >> "%LOG%"
set STRICT_EVIDENCE=1
set COLUMNS=110
%PY% chat.py --demo --no-pause --save-html docs\demo.html >> "%LOG%" 2>&1

if not exist results\evidence mkdir results\evidence
copy /y outputs\eval_report*_ev0.json results\evidence\ >> "%LOG%" 2>&1
copy /y outputs\eval_report*_ev1.json results\evidence\ >> "%LOG%" 2>&1
echo RESULT DONE >> "%LOG%"
echo END %date% %time% >> "%LOG%"
copy /y "%LOG%" results\evidence\evidence_log.txt >nul 2>&1
goto :eof

:run
echo ==== STRICT_EVIDENCE=%1 >> "%LOG%"
set STRICT_EVIDENCE=%1
%PY% eval.py --tag ev%1 >> "%LOG%" 2>&1
%PY% eval.py --file data\eval\heldout.jsonl --tag ev%1 >> "%LOG%" 2>&1
%PY% eval.py --file data\eval\final_check.jsonl --tag ev%1 >> "%LOG%" 2>&1
exit /b
