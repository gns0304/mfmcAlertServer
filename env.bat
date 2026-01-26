@echo off
REM ===============================
REM MFMC Client Environment
REM ===============================
set MFMC_SERVER=http://127.0.0.1:8000
set MFMC_USERNAME=device01
set MFMC_PASSWORD=
set MFMC_POLL_INTERVAL=5
set MFMC_REQUEST_TIMEOUT=5
set MFMC_HEARTBEAT_INTERVAL_SEC=300
set MFMC_SERVER_LOG_MIN_LEVEL=INFO

REM exe 실행
client_windows.exe