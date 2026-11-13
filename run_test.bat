@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set COLUMNS=150
set LOG=%~dp0test_log.txt
echo START %date% %time% > "%LOG%"
echo ==== GPU >> "%LOG%"
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv >> "%LOG%" 2>&1
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY (python --version >nul 2>&1 && set PY=python)
if not defined PY (echo RESULT NO_PYTHON >> "%LOG%" & goto end)
echo ==== PYTHON >> "%LOG%"
%PY% --version >> "%LOG%" 2>&1
echo ==== OLLAMA >> "%LOG%"
where ollama >> "%LOG%" 2>&1
if errorlevel 1 (echo RESULT NO_OLLAMA >> "%LOG%" & goto end)
ollama --version >> "%LOG%" 2>&1
ollama list >> "%LOG%" 2>&1
echo ==== VENV >> "%LOG%"
if not exist .venv\Scripts\python.exe %PY% -m venv .venv >> "%LOG%" 2>&1
.venv\Scripts\python.exe -m pip install -q -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 (echo RESULT PIP_FAILED >> "%LOG%" & goto end)
echo ==== CHECK_SETUP >> "%LOG%"
.venv\Scripts\python.exe tools\check_setup.py > check_setup.log 2>&1
type check_setup.log >> "%LOG%"
findstr /C:"[FAIL]" check_setup.log >nul && (echo RESULT SETUP_FAILED >> "%LOG%" & goto end)
echo ==== PREP >> "%LOG%"
.venv\Scripts\python.exe prep.py >> "%LOG%" 2>&1
if errorlevel 1 (echo RESULT PREP_FAILED >> "%LOG%" & goto end)
echo ==== FIDELITY >> "%LOG%"
.venv\Scripts\python.exe tools\check_clean_fidelity.py >> "%LOG%" 2>&1
echo ==== EVAL >> "%LOG%"
.venv\Scripts\python.exe eval.py --sweep >> "%LOG%" 2>&1
echo ==== OLLAMA_PS >> "%LOG%"
ollama ps >> "%LOG%" 2>&1
echo RESULT DONE >> "%LOG%"
:end
echo END %date% %time% >> "%LOG%"
