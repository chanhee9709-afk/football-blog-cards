"""Task Scheduler entry for auto_save.py without wscript/cmd (11/16: the company PC refused run_hidden.vbs
with 'Microsoft VBScript 800A0046 사용 권한이 없습니다' every run). pythonw.exe shows no window and no popups.
Install: double-click install_task.bat (once)."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
os.environ["PYTHONIOENCODING"] = "utf-8"
log = open(HERE / "auto_save.log", "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = log
sys.path.insert(0, str(HERE))
try:
    import auto_save
    auto_save.main()
except SystemExit:
    pass
except Exception:
    import traceback
    traceback.print_exc()
