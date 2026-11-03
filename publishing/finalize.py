"""Check a v2 draft (post.md with front-matter) and build the files publishing needs.

Usage: python3 -I finalize.py <draft dir> [--force]
Rules: /mnt/project-files/blog-style/draft-format.md. BLOCK stops the build, WARN only reports.
Writes into the draft dir: publish.json (for naver_publish.py), post-paste.txt and 발행정보.txt
(the old manual-paste files, so james can still post by hand).
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

GREETING = "안녕하세요! 제임스입니다~"
CATEGORIES = ["이적시장", "경기 리뷰·논평", "일정·프리뷰", "축구 상식", "데이터로 보는 축구"]
POST_TYPES = ["preview", "review", "transfer", "issue", "data", "basics"]
MIN_CHARS, TARGET_CHARS = 2300, 2800
TITLE_MAX, SENT_MAX, INTRO_MIN, SECTION_MAX, MIN_TAGS = 32, 45, 80, 8, 10
ALLOWED_DOMAINS = [
    # 영어권 · 유럽 언론
    "theguardian.com", "bbc.co.uk", "bbc.com", "skysports.com", "espn.com", "espn.co.uk", "nytimes.com",
    "theathletic.com", "independent.co.uk", "telegraph.co.uk", "reuters.com", "apnews.com", "goal.com",
    "sportschau.de", "sport1.de", "kicker.de", "bild.de", "leparisien.fr", "lequipe.fr", "rmcsport.bfmtv.com",
    "skysport.it", "sport.sky.it", "gazzetta.it", "corrieredellosport.it", "marca.com", "as.com",
    "mundodeportivo.com", "sport.es", "relevo.com",
    # 리그 · 협회 · 데이터
    "premierleague.com", "laliga.com", "bundesliga.com", "legaseriea.it", "ligue1.com", "ligue1.fr",
    "uefa.com", "fifa.com", "kfa.or.kr", "mlssoccer.com", "api-football.com", "football-data.org",
    "fbref.com", "transfermarkt.com", "transfermarkt.de", "sofascore.com", "whoscored.com", "opta.com",
    # 한국 언론
    "yna.co.kr", "naver.com", "chosun.com", "donga.com", "joongang.co.kr", "hani.co.kr", "osen.co.kr",
    "starnewskorea.com", "spotvnews.co.kr", "xportsnews.com", "mydaily.co.kr", "sportalkorea.com",
    "interfootball.co.kr", "footballist.co.kr", "besteleven.com", "sportsseoul.com", "isplus.com",
    "news1.kr", "newsis.com", "mk.co.kr", "hankyung.com",
    # 1티어 기자(로마노 등) 게시물
    "x.com", "twitter.com",
]
HOMEWORK_ENDINGS = ("보세요", "확인하세요", "챙기세요", "알아보세요")
SELF_TALK = ["짚어 볼게요", "짚어볼게요", "정리해 둘게요", "정리해 볼게요", "정리해볼게요", "핵심은 하나",
             "알아보겠습니다", "알아볼게요", "많은 분들이 궁금해"]
BETTING = ["토토", "배팅", "베팅", "배당률", "픽 추천"]
VAGUE_ASKS = ["어떻게 보시나요", "어떻게 생각하시나요", "여러분 생각은", "여러분의 생각은"]
STYLE_WORDS = ["watercolor", "illustration", "cartoon", "anime", "3d render", "3d", "painting", "sketch", "vector"]
ROOT_CAUSE_WORDS = ["전술", "포메이션", "역할", "원인", "이유", "압박", "빌드업", "라인"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def load(draft):
    text = (draft / "post.md").read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        sys.exit("post.md must start with a --- front-matter block")
    return yaml.safe_load(m.group(1)) or {}, m.group(2).strip()


def plain(line):
    """Text as a reader sees it: no markdown marks."""
    line = re.sub(r"^#{1,6}\s*|^>\s*|^[-*]\s+|^\d+\.\s+", "", line.strip())
    return line.replace("**", "").replace("|", " ").strip()


def sentences(lines):
    out = []
    for ln in lines:
        s = ln.strip()
        if not s or s == "[IMAGE]" or s.startswith("|") or s.startswith("#"):
            continue
        out += [x for x in re.split(r"(?<=[.?!])\s+", plain(s)) if x]
    return out


def split_sections(body):
    """[(heading or None for intro, level, [lines])]"""
    secs, cur = [], (None, 0, [])
    for ln in body.splitlines():
        m = re.match(r"^(#{2,3})\s+(.*)", ln)
        if m:
            secs.append(cur)
            cur = (m.group(2).strip(), len(m.group(1)), [])
        else:
            cur[2].append(ln)
    secs.append(cur)
    return secs


def check(fm, body, draft):
    block, warn = [], []
    title = str(fm.get("title", "")).strip()
    kws = fm.get("keywords") or []
    kw = str(kws[0]) if kws else ""
    tags = [str(t).strip().lstrip("#").replace(" ", "") for t in fm.get("tags") or []]
    ptype = fm.get("post_type", "")
    secs = split_sections(body)
    intro_lines = secs[0][2]
    h2 = [h for h, lv, _ in secs if h and lv == 2]

    # 정보 칸
    for k in ("title", "category", "post_type", "summary", "keywords", "tags", "sources", "thumbnail_prompt"):
        if not fm.get(k):
            block.append(f"정보 칸 '{k}'이 비어 있어요")
    if fm.get("category") and fm["category"] not in CATEGORIES:
        block.append(f"category '{fm['category']}'는 5개 카테고리 중 하나가 아니에요")
    if ptype and ptype not in POST_TYPES:
        block.append(f"post_type '{ptype}'는 {POST_TYPES} 중 하나여야 해요")

    # 분량
    count_lines = [plain(l) for l in body.splitlines() if l.strip() and l.strip() != "[IMAGE]"
                   and not re.fullmatch(r"\|?[\s:\-|]+\|?", l.strip())]
    n = sum(len(l) for l in count_lines)
    if n < MIN_CHARS:
        block.append(f"분량 {n:,}자: {MIN_CHARS:,}자 미만이에요 (목표 {TARGET_CHARS:,}자)")

    # 제목
    if len(title) > TITLE_MAX:
        warn.append(f"제목 {len(title)}자: {TITLE_MAX}자 넘으면 검색 결과에서 잘려요")
    if title.rstrip("?!. ").endswith(HOMEWORK_ENDINGS):
        block.append("제목이 '~보세요/확인하세요' 같은 숙제형으로 끝나요")

    # 도입부
    if not intro_lines or intro_lines[0].strip() != GREETING:
        warn.append(f"첫 줄이 인사 '{GREETING}'가 아니에요")
    intro = " ".join(plain(l) for l in intro_lines if l.strip() and l.strip() not in (GREETING, "[IMAGE]"))
    if len(intro) < INTRO_MIN:
        block.append(f"도입부 {len(intro)}자: 첫 소제목 앞에 {INTRO_MIN}자 이상 써야 해요")
    if kw and kw.replace(" ", "") not in (title + intro).replace(" ", ""):
        block.append(f"대표 키워드 '{kw}'가 제목에도 도입부에도 없어요")
    if kw and sum(kw.replace(" ", "") in h.replace(" ", "") for h in h2) < 2:
        warn.append(f"대표 키워드 '{kw}'가 들어간 소제목이 2개 미만이에요")
    if kw and kw.replace(" ", "") not in tags:
        warn.append(f"대표 키워드 '{kw}'가 태그에 없어요")

    # 소제목 · 구간 길이
    if len(h2) < 4:
        warn.append(f"소제목이 {len(h2)}개예요 (5~7개 기준)")
    for h, lv, lines in secs[1:]:
        if h == "자주 묻는 질문":
            continue
        k = len(sentences(lines))
        if k > SECTION_MAX:
            block.append(f"'{h}' 구간 {k}문장: {SECTION_MAX}문장 넘으면 소제목을 나눠요")
    if "# " in body.splitlines()[0] or any(re.match(r"^#\s", l) for l in body.splitlines()):
        block.append("본문에 '# 문서 제목'은 넣지 않아요 (소제목은 ##)")

    # 문장
    all_sents = sentences(body.splitlines())
    long_s = [s for s in all_sents if len(s) > SENT_MAX]
    if long_s:
        warn.append(f"{SENT_MAX}자 넘는 문장 {len(long_s)}개 (예: '{long_s[0][:30]}…')")
    formal = [s for s in all_sents if re.search(r"(습니다|입니다|합니다)[.!?]?$", s)]
    if formal:
        warn.append(f"합니다체 문장 {len(formal)}개가 섞였어요 (예: '{formal[0][:30]}…')")
    for w in SELF_TALK:
        if w in body:
            warn.append(f"글이 자기를 설명하는 말 '{w}'")
    for w in BETTING:
        if w in body:
            block.append(f"베팅 관련 표현 '{w}'은 쓰지 않아요")
    if EMOJI.search(body):
        warn.append("본문에 이모티콘이 있어요")
    if not any(l.strip().startswith("|") for l in body.splitlines()):
        warn.append("표가 하나도 없어요")
    if not any(w in body for w in ROOT_CAUSE_WORDS):
        warn.append("원인 분석(전술·역할·포메이션) 말이 안 보여요")

    # 꼭 들어가는 구간
    names = [h for h in h2]
    if ptype == "preview" and not any("관전 포인트" in h for h in names):
        block.append("프리뷰에는 '관전 포인트' 구간이 있어야 해요")
    think = [i for i, h in enumerate(names) if h.startswith("제임스의 생각")]
    faq = [i for i, h in enumerate(names) if h == "자주 묻는 질문"]
    if not think:
        block.append("'제임스의 생각' 구간이 없어요")
    else:
        if faq and think[0] != faq[0] - 1:
            block.append("'제임스의 생각'은 '자주 묻는 질문' 바로 앞이어야 해요")
        if not faq and think[0] != len(names) - 1:
            block.append("'제임스의 생각'은 마지막 구간(또는 FAQ 바로 앞)이어야 해요")
        lines = next(l for h, lv, l in secs if h == names[think[0]])
        txt = [l.strip() for l in lines if l.strip() and not l.strip().startswith("|")]
        if not txt or not re.match(r"^\*\*저는.*\*\*$", txt[0]):
            block.append("'제임스의 생각' 첫 줄은 '**저는 …**' 굵은 판단 한 줄이어야 해요")
        if not txt or not txt[-1].endswith("?"):
            block.append("'제임스의 생각' 마지막 줄은 3초 안에 답할 질문이어야 해요")
        elif any(v in txt[-1] for v in VAGUE_ASKS):
            block.append("'어떻게 보시나요?'류 질문 대신 둘 중 하나 고르는 질문을 써요")
        if not any(l.startswith("다만") for l in txt):
            warn.append("'제임스의 생각'에 '다만'(반대 근거)이 없어요")
        if not any(l.strip().startswith("|") for l in lines):
            warn.append("'제임스의 생각'에 생각을 바꿀 조건 표가 없어요")
        if ptype == "preview" and not re.search(r"\d\s*(대|-|:)\s*\d", " ".join(txt)):
            warn.append("프리뷰 '제임스의 생각'에 스코어 예상이 안 보여요")
    if not faq:
        warn.append("'자주 묻는 질문' 구간이 없어요")
    elif faq[0] != len(names) - 1:
        warn.append("'자주 묻는 질문'은 맨 끝이어야 해요")

    # 태그
    if len(tags) < MIN_TAGS:
        block.append(f"태그 {len(tags)}개: 발행정보 태그는 전부(보통 16개) 넣어요")
    if re.search(r"^#\S+(\s+#\S+){2,}\s*$", body, re.M):
        warn.append("본문에 태그 줄이 있어요: 태그 줄은 코드가 자동으로 붙이니 지워요")

    # 출처
    srcs = fm.get("sources") or []
    if len(srcs) < 2:
        block.append(f"출처 URL {len(srcs)}개: 2개 이상 필요해요")
    for u in srcs:
        host = (urlparse(str(u)).hostname or "").lower()
        if not any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS):
            block.append(f"허용 목록 밖 출처: {u}")
    if not fm.get("source_note"):
        warn.append("source_note(출처 기관 한 줄)가 비어 있어요")

    # 그림
    slots = body.count("[IMAGE]")
    imgs = fm.get("images") or []
    if slots != len(imgs):
        block.append(f"[IMAGE] {slots}자리인데 images는 {len(imgs)}개예요")
    for im in imgs:
        if not (draft / str(im.get("file", ""))).exists():
            block.append(f"그림 파일 없음: {im.get('file')}")
    for i, ln in enumerate(body.splitlines()):
        if ln.strip() == "[IMAGE]":
            nxt = next((l for l in body.splitlines()[i + 1:] if l.strip()), "")
            if not nxt.startswith("## "):
                warn.append(f"[IMAGE] 다음이 소제목이 아니에요 ({i + 1}번째 줄)")
    tp = str(fm.get("thumbnail_prompt", ""))
    if re.search("[가-힣]", tp):
        block.append("thumbnail_prompt에 한글이 있어요 (영어로만)")
    low = tp.lower()
    for w in STYLE_WORDS:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            block.append(f"thumbnail_prompt에 그림체 말 '{w}' (실사로)")
    if tp and "no logos" not in low and "no logo" not in low:
        warn.append("thumbnail_prompt에 'No logos, no crests' 문구가 없어요")
    if fm.get("thumbnail_file") and not (draft / fm["thumbnail_file"]).exists():
        block.append(f"썸네일 파일 없음: {fm['thumbnail_file']}")

    # 쓰레드
    th = str(fm.get("threads_text") or "").strip()
    if th:
        if len(th) > 500:
            block.append(f"threads_text {len(th)}자: 500자 안")
        if re.search(r"https?://|www\.", th):
            block.append("threads_text에 링크가 있어요 (링크는 코드가 댓글로)")
        if re.search(r"(요|니다)[.!?]?(\s|$)", th):
            block.append("threads_text는 반말로 ('~요/~니다' 없이)")
        tags_th = re.findall(r"#\S+", th)
        if len(tags_th) != 1:
            block.append(f"threads_text 해시태그 {len(tags_th)}개: 맨 끝 하나만")
        before = re.sub(r"#\S+\s*$", "", th).strip().splitlines()
        if not before or not before[-1].rstrip().rstrip("👀📅⚽🔥").strip().endswith("?"):
            block.append("threads_text 해시태그 앞 마지막 줄이 질문이 아니에요")
    return block, warn, n


def build(fm, body, draft):
    tags = [str(t).strip().lstrip("#").replace(" ", "") for t in fm["tags"]]
    tag_line = " ".join("#" + t for t in tags)
    footer = f"출처: {fm.get('source_note', '')}" + (f" (기록은 {fm['data_as_of']} 기준)" if fm.get("data_as_of") else "")
    blocks, img_i, first_h = [], 0, True
    if fm.get("thumbnail_file"):
        blocks.append({"type": "image", "file": fm["thumbnail_file"], "cover": True})
    for ln in body.splitlines():
        s = ln.rstrip()
        if not s.strip():
            continue
        if s.strip() == "[IMAGE]":
            blocks.append({"type": "image", "file": fm["images"][img_i]["file"],
                           "caption": fm["images"][img_i].get("caption", "")})
            img_i += 1
        elif s.startswith("## "):
            blocks.append({"type": "quote", "style": "frame" if first_h else "quote", "text": s[3:].strip()})
            first_h = False
        elif s.startswith("### "):
            blocks.append({"type": "text", "text": s[4:].strip(), "bold": True})
        elif s.startswith("> "):
            blocks.append({"type": "quote", "style": "line", "text": s[2:].strip()})
        elif s.startswith("|"):
            if re.fullmatch(r"\|?[\s:\-|]+\|?", s.strip()):
                continue
            row = [c.strip() for c in s.strip().strip("|").split("|")]
            if blocks and blocks[-1]["type"] == "table":
                blocks[-1]["rows"].append(row)
            else:
                blocks.append({"type": "table", "rows": [row]})
        else:
            bold = bool(re.fullmatch(r"\*\*.*\*\*", s.strip()))
            blocks.append({"type": "text", "text": plain(s), "bold": bold})
    blocks.append({"type": "text", "text": footer, "small": True})
    blocks.append({"type": "text", "text": tag_line})
    pub = {k: fm.get(k) for k in ("title", "category", "publish_at", "threads_text", "thumbnail_text")}
    pub.update(tags=tags, blocks=blocks, sources=fm["sources"])
    (draft / "publish.json").write_text(json.dumps(pub, ensure_ascii=False, indent=1), encoding="utf-8")

    # 손으로 붙여 넣을 때 쓰는 예전 형식
    paste, n_img = ["[썸네일 넣기 (대표 이미지로 지정)]", ""], 0
    for b in blocks:
        if b["type"] == "image" and not b.get("cover"):
            n_img += 1
            paste += [f"[사진 {n_img}번 넣기]", ""]
        elif b["type"] == "quote":
            paste += [("【소제목】 " if b["style"] != "line" else "▌") + b["text"], ""]
        elif b["type"] == "table":
            paste += [" | ".join(r) for r in b["rows"]] + [""]
        elif b["type"] == "text":
            paste += [b["text"], ""]
    (draft / "post-paste.txt").write_text("\n".join(paste).rstrip() + "\n", encoding="utf-8")
    info = [f"카테고리: {fm['category']}", "", f"제목: {fm['title']}", "",
            f"예약 발행: {fm.get('publish_at') or '바로'}", "", f"태그 ({len(tags)}개)", ", ".join(tags), "",
            "이미지 순서", "- 썸네일: " + (fm.get("thumbnail_file") or "Gemini 이미지를 보내 주시면 만들어 드려요")]
    info += [f"- 사진 {i + 1}: {im['file']} ({im.get('caption', '')})" for i, im in enumerate(fm["images"])]
    info += ["", "AI 이미지 프롬프트 (Gemini, 4:5)", str(fm["thumbnail_prompt"]), "",
             "썸네일 문구", " / ".join(fm.get("thumbnail_text") or [])]
    (draft / "발행정보.txt").write_text("\n".join(info) + "\n", encoding="utf-8")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    draft = Path(args[0])
    fm, body = load(draft)
    block, warn, n = check(fm, body, draft)
    print(f"분량 {n:,}자 · 제목 {len(str(fm.get('title', '')))}자")
    for w in warn:
        print("[경고]", w)
    for b in block:
        print("[막힘]", b)
    if block and "--force" not in sys.argv:
        sys.exit(f"막힘 {len(block)}개: 고친 뒤 다시 돌려요")
    build(fm, body, draft)
    print("OK: publish.json · post-paste.txt · 발행정보.txt 만들었어요"
          + ("" if fm.get("thumbnail_file") else " (썸네일 대기 중)"))


if __name__ == "__main__":
    main()
