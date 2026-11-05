"""Auto 임시저장 for james's PC: picks up new drafts Claude pushes and saves them to Naver as 임시저장.

Runs every 10 minutes from Windows 작업 스케줄러 (see install line below). Each run:
  1. lists the public repo's claude/* branches and reads the ones that changed (GitHub API, no login),
  2. finds publishing/drafts/<YYYY-MM-DD-N>/ folders dated today or yesterday (KST),
  3. downloads any folder that is new or changed since the last run into drafts\\<name>,
  4. runs `python naver_publish.py drafts\\<name>` (임시저장 only, never 발행),
  5. remembers the folder's git hash in auto_save_done.json so it is not saved twice.
A changed folder (e.g. Gemini thumbnail swapped in) is saved again as a NEW 임시저장 글: use the newest one.
james then opens the Naver blog app > 글쓰기 > 임시저장, picks the category and presses 발행.

Install (cmd, once, in C:\\Users\\Intellian\\naver-publish):
  schtasks /create /tn NaverAutoSave /sc minute /mo 10 /f /tr "cmd /c cd /d C:\\Users\\Intellian\\naver-publish && set PYTHONIOENCODING=utf-8 && python auto_save.py >> auto_save.log 2>&1"
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
        fails = state.setdefault("fails", {})
        if done.get(name) == sha or fails.get(name + "@" + sha, 0) >= 3:
            continue
        files = [t for t in get(f"{API}/git/trees/{sha}")["tree"] if t["type"] == "blob"]
        if not any(f["path"] == "publish.json" for f in files):
            log(name, "publish.json 없음, 건너뜀")
            done[name] = sha
            continue
        out = DRAFTS / name
        out.mkdir(parents=True, exist_ok=True)
        for f in files:
            url = f"https://raw.githubusercontent.com/{REPO}/{commit_sha}/{path}/{urllib.request.quote(f['path'])}"
            (out / f["path"]).write_bytes(get(url, raw=True))
        log(name, f"{len(files)}개 파일 받음, 임시저장 시작")
        r = subprocess.run([sys.executable, str(HERE / "naver_publish.py"), str(out)], stdin=subprocess.DEVNULL)
        if r.returncode == 0:
            done[name] = sha
            DONE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            log(name, "임시저장 끝")
        else:
            fails[name + "@" + sha] = fails.get(name + "@" + sha, 0) + 1
            log(name, f"실패 (코드 {r.returncode}), {fails[name + '@' + sha]}/3번째. 3번 실패하면 멈춰요")
    DONE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    if all(done.get(k) == v[0] for k, v in found.items()):
        log("새 원고 없음")


if __name__ == "__main__":
    main()
