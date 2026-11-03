"""Post a finalized draft to Naver Blog through the SmartEditor ONE web editor (Playwright).

Naver has no posting API, so this drives the real editor like koni's publisher does.
Run it on james's own computer: the Naver login lives in a browser profile there and never leaves it.

  pip install playwright pyyaml && python -m playwright install chromium
  python naver_publish.py --login                 # once: a window opens, james logs in himself
                                                  #   (check "로그인 상태 유지"), then closes the window
  python naver_publish.py <draft dir>             # fill the editor and press 임시저장 only (default)
  python naver_publish.py <draft dir> --publish   # also press 발행 (예약 if publish_at is set)

<draft dir> must hold publish.json from finalize.py plus the image files.
What it does (koni's list): first ## -> 인용구 '프레임', other ## -> '따옴표', > -> '버티컬 라인',
optional body font (--font 마루부리), cover image on top, [IMAGE] slots filled, tables drawn as
images, footer source line + #tag line, tag box + category filled.
SmartEditor class names change now and then; all selectors sit in SEL so a fix is one line.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BLOG_ID = "chanheejk"
PROFILE = Path.home() / ".naver-publish-profile"
WRITE_URL = f"https://blog.naver.com/PostWriteForm.naver?blogId={BLOG_ID}"
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

SEL = {
    "frame": "#mainFrame",
    "draft_popup_cancel": ".se-popup-button-cancel",
    "help_close": ".se-help-panel-close-button",
    "title": ".se-documentTitle .se-text-paragraph",
    "body_first": ".se-component.se-text .se-text-paragraph",
    "quote_menu": "button.se-insert-menu-button-quotation, button[data-name='quotation'] + button",
    "quote_style": {  # SmartEditor quotation layouts
        "quote": "button[data-value='default']",
        "line": "button[data-value='quotation_line']",
        "frame": "button[data-value='quotation_corner']",
    },
    "image_button": "button.se-image-toolbar-button, button[data-name='image']",
    "font_button": "button.se-font-family-toolbar-button",
    "font_option": "button.se-toolbar-option-font-family-{name}-button",
    "save": "button[class*='save_btn']",
    "publish": "button[class*='publish_btn']",
    "category_open": "button[class*='selectbox_button']",
    "category_item": "span[class*='text__']",
    "tag_input": "#tag-input",
    "reserve_radio": "label[for='radio_time2']",
    "reserve_hour": "select[class*='hour_option']",
    "reserve_minute": "select[class*='minute_option']",
    "reserve_date": "input[class*='input_date']",
    "confirm": "button[class*='confirm_btn']",
}
FONT_NAMES = {"마루부리": "maruburi", "나눔고딕": "nanumgothic", "나눔명조": "nanummyeongjo"}


def table_png(browser, rows, out):
    """SmartEditor tables are fiddly to drive, so draw the table as an image in the blog's style."""
    font = (FONT_DIR / "Pretendard-Regular.otf").as_uri()
    bold = (FONT_DIR / "Pretendard-Bold.otf").as_uri()
    head = "".join(f"<th>{c}</th>" for c in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows[1:])
    html = f"""<html><head><style>
@font-face{{font-family:P;src:url({font})}} @font-face{{font-family:P;font-weight:700;src:url({bold})}}
body{{margin:0;padding:24px;background:#fff;font-family:P;width:860px}}
table{{border-collapse:collapse;width:100%;font-size:22px}}
th{{background:#0F2A4A;color:#fff;font-weight:700;padding:14px;text-align:left}}
td{{border-bottom:1px solid #d9dee5;padding:14px;color:#1b1f24}} tr:nth-child(even) td{{background:#f4f6f9}}
</style></head><body><table><tr>{head}</tr>{body}</table></body></html>"""
    page = browser.new_page(viewport={"width": 908, "height": 400})
    page.set_content(html)
    page.locator("body").screenshot(path=str(out))
    page.close()


def type_lines(page, text, bold=False):
    if bold:
        page.keyboard.press("Control+b")
    page.keyboard.insert_text(text)
    if bold:
        page.keyboard.press("Control+b")
    page.keyboard.press("Enter")


def add_quote(page, ed, style, text):
    ed.locator(SEL["quote_menu"]).first.click()
    ed.locator(SEL["quote_style"][style]).first.click()
    time.sleep(0.4)
    page.keyboard.insert_text(text)
    # leave the quote box: click below the last component, or arrow out
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    time.sleep(0.2)


def add_image(page, ed, path):
    with page.expect_file_chooser() as fc:
        ed.locator(SEL["image_button"]).first.click()
    fc.value.set_files(str(path))
    page.wait_for_timeout(2500)  # upload
    page.keyboard.press("End")
    page.keyboard.press("Enter")


def fill(page, ed, pub, draft, browser, font):
    ed.locator(SEL["title"]).first.click()
    page.keyboard.insert_text(pub["title"])
    ed.locator(SEL["body_first"]).first.click()
    tmp = draft / "_tables"
    tmp.mkdir(exist_ok=True)
    for i, b in enumerate(pub["blocks"]):
        if b["type"] == "text":
            type_lines(page, b["text"], b.get("bold"))
            if not b.get("small"):
                page.keyboard.press("Enter")  # blank line between sentences (one sentence = one paragraph)
        elif b["type"] == "quote":
            add_quote(page, ed, b["style"], b["text"])
        elif b["type"] == "image":
            add_image(page, ed, draft / b["file"])
        elif b["type"] == "table":
            out = tmp / f"table-{i}.png"
            table_png(browser, b["rows"], out)
            add_image(page, ed, out)
    if font:
        page.keyboard.press("Control+a")
        ed.locator(SEL["font_button"]).first.click()
        ed.locator(SEL["font_option"].format(name=FONT_NAMES[font])).first.click()


def publish_dialog(page, ed, pub, really):
    ed.locator(SEL["publish"]).first.click()
    page.wait_for_timeout(800)
    ed.locator(SEL["category_open"]).first.click()
    ed.locator(SEL["category_item"], has_text=pub["category"]).first.click()
    tag_box = ed.locator(SEL["tag_input"])
    for t in pub["tags"][:30]:  # Naver allows 30 tags
        tag_box.click()
        page.keyboard.insert_text(t)
        page.keyboard.press("Enter")
    if pub.get("publish_at"):
        day, hm = pub["publish_at"].split()
        h, m = hm.split(":")
        ed.locator(SEL["reserve_radio"]).first.click()
        ed.locator(SEL["reserve_date"]).first.fill(day.replace("-", "."))
        ed.locator(SEL["reserve_hour"]).first.select_option(h.zfill(2))
        ed.locator(SEL["reserve_minute"]).first.select_option(str(int(m) // 10 * 10).zfill(2))
    if really:
        ed.locator(SEL["confirm"]).first.click()
        page.wait_for_timeout(4000)
        print("발행 완료:", page.url)
    else:
        print("발행 창까지 채웠어요. 확인하고 직접 '발행'을 눌러 주세요.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft", nargs="?")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--publish", action="store_true", help="press 발행 (default: 임시저장 only)")
    ap.add_argument("--review", action="store_true", help="open the 발행 dialog filled, james presses the button")
    ap.add_argument("--font", choices=list(FONT_NAMES), default=None)
    a = ap.parse_args()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=False, locale="ko-KR",
                                                   viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if a.login:
            page.goto("https://nid.naver.com/nidlogin.login")
            print("창에서 직접 로그인하고('로그인 상태 유지' 체크) 창을 닫아 주세요.")
            page.wait_for_event("close", timeout=0)
            return
        if not a.draft:
            sys.exit(__doc__)
        draft = Path(a.draft)
        pub = json.loads((draft / "publish.json").read_text(encoding="utf-8"))
        if not any(b.get("cover") for b in pub["blocks"]):
            sys.exit("썸네일(thumbnail_file)이 아직 없어요: james의 Gemini 이미지가 오면 finalize부터 다시 돌려요")
        page.goto(WRITE_URL)
        if "nid.naver.com" in page.url:
            sys.exit("로그인이 풀렸어요: --login 으로 다시 로그인해 주세요")
        ed = page.frame_locator(SEL["frame"])
        page.wait_for_timeout(3000)
        for key in ("draft_popup_cancel", "help_close"):
            if ed.locator(SEL[key]).count():
                ed.locator(SEL[key]).first.click()
        browser = ctx.browser or p.chromium.launch()
        fill(page, ed, pub, draft, browser, a.font)
        if a.publish or a.review:
            publish_dialog(page, ed, pub, a.publish)
        else:
            ed.locator(SEL["save"]).first.click()
            print("임시저장했어요. 네이버 글쓰기 > 임시저장 글에서 확인해 주세요.")
        input("엔터를 누르면 창을 닫아요…")
        ctx.close()


if __name__ == "__main__":
    main()
