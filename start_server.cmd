@echo off
cd /d "%~dp0"
"C:\Users\Hao-Yun Zou\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" server.py --port 8023 >> data\server.log 2>&1
