@echo off
cd /d C:\Users\Intellian\naver-publish
set PYW=
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (
  echo pythonw.exe not found. Tell Claude.
  pause
  exit /b 1
)
echo pythonw: %PYW%
schtasks /create /tn NaverAutoSave /sc minute /mo 10 /f /tr "\"%PYW%\" \"C:\Users\Intellian\naver-publish\run_auto_save.pyw\""
echo.
echo Done. You can close this window.
pause
