"""Auto 임시저장 for james's PC: picks up new drafts Claude pushes and saves them to Naver as 임시저장.

Runs every 10 minutes from Windows 작업 스케줄러 (see install line below). Each run:
  1. lists the public repo's claude/* branches and reads the ones that changed (GitHub API, no login),
  2. finds publishing/drafts/<YYYY-MM-DD-N>/ folders dated today or yesterday (KST),
  3. downloads any folder that is new or changed since the last run into drafts\\<name>,
  4. runs `python naver_publish.py drafts\\<name>` (임시저장 only, never 발행),
  5. remembers the folder NAME in auto_save_done.json: each folder is tried exactly once, ever.
     (james 11/6: 8 duplicate 임시저장 copies) A re-pushed or changed folder is NOT saved again,
     and a failed run is not retried automatically. To save an updated draft, Claude pushes it
     under a new folder name (e.g. 2026-11-06-1b).
james then opens the Naver blog app > 글쓰기 > 임시저장, picks the category and presses 발행.

Install (cmd, once, in C:\\Users\\Intellian\\naver-publish). run_hidden.vbs runs it with no console window:
  schtasks /create /tn NaverAutoSave /sc minute /mo 10 /f /tr "wscript C:\\Users\\Intellian\\naver-publish\\run_hidden.vbs"
Remove: schtasks /delete /tn NaverAutoSave /f
Needs the PC on and james logged in to Windows (Chrome opens a window while it types).
"""
import datetime
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "chanhee9709-afk/football-blog-cards"
API = f"https://api.github.com/repos/{REPO}"
HERE = Path(__file__).resolve().parent
DRAFTS = HERE / "drafts"
DONE = HERE / "auto_save_done.json"
KST = datetime.timezone(datetime.timedelta(hours=9))


def get(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "naver-auto-save", "Accept": "application/vnd.github+json"})
    data = urllib.request.urlopen(req, timeout=30).read()
    return data if raw else json.loads(data)


def log(*a):
    print(datetime.datetime.now(KST).strftime("%m/%d %H:%M"), *a, flush=True)


def main():
    state = json.loads(DONE.read_text(encoding="utf-8")) if DONE.exists() else {}
    done, heads, seen = state.setdefault("done", {}), state.setdefault("heads", {}), state.setdefault("seen", {})
    today = datetime.datetime.now(KST).date()
    days = {str(today), str(today - datetime.timedelta(days=1))}
    # only branches whose head moved since the last run cost an API call (GitHub allows 60/hour without login)
    for br in get(f"{API}/branches?per_page=100"):
        name, head = br["name"], br["commit"]["sha"]
        if not name.startswith("claude/") or heads.get(name) == head:
            continue
        heads[name] = head
        for t in get(f"{API}/git/trees/{head}?recursive=1")["tree"]:
            parts = t["path"].split("/")
            if t["type"] == "tree" and len(parts) == 3 and parts[:2] == ["publishing", "drafts"]:
                seen[parts[2]] = [t["sha"], head, t["path"]]
    found = {k: v for k, v in seen.items() if k[:10] in days}
    for name in sorted(found):
        sha, commit_sha, path = found[name]
        if name in done:
            continue
        files = [t for t in get(f"{API}/git/trees/{sha}")["tree"] if t["type"] == "blob"]
        if not any(f["path"] == "publish.json" for f in files):
            log(name, "publish.json 없음, 건너뜀")
            continue
        out = DRAFTS / name
        out.mkdir(parents=True, exist_ok=True)
        for f in files:
            url = f"https://raw.githubusercontent.com/{REPO}/{commit_sha}/{path}/{urllib.request.quote(f['path'])}"
            (out / f["path"]).write_bytes(get(url, raw=True))
        # mark as done BEFORE typing, so a crash or error mid-save can never cause a second copy
        done[name] = sha
        DONE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        log(name, f"{len(files)}개 파일 받음, 임시저장 시작")
        r = subprocess.run([sys.executable, str(HERE / "naver_publish.py"), str(out)], stdin=subprocess.DEVNULL)
        if r.returncode == 0:
            log(name, "임시저장 끝")
        else:
            log(name, f"실패 (코드 {r.returncode}). 다시 시도하지 않아요: 임시저장 목록 확인 후 Claude에게 말해 주세요")
    DONE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    if all(k in done for k in found):
        log("새 원고 없음")


if __name__ == "__main__":
    main()
