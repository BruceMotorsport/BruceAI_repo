@echo off
rem Groq Pool Bridge — one OpenAI-compatible endpoint for several Groq accounts.
rem Keys: groq_keys.txt or GROQ_KEYS in .env. Health: http://127.0.0.1:8081/health
cd /d "%~dp0"
if not exist logs mkdir logs
start "GroqPool" /min cmd /c ""C:\Users\User\AppData\Local\Programs\Python\Python311\python.exe" groq_pool.py --port 8081 >> logs\groq_pool.out.log 2>&1"
echo Groq Pool Bridge starting on http://127.0.0.1:8081
echo Logs: logs\groq_pool.out.log
