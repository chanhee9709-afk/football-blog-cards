' Runs auto_save.py with no console window (Task Scheduler: wscript run_hidden.vbs)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Intellian\naver-publish"
sh.Run "cmd /c set PYTHONIOENCODING=utf-8&& python auto_save.py >> auto_save.log 2>&1", 0, True
