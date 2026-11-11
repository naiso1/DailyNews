"""Exercise real news UI/client against an isolated API (never writes to production).

Run with the DailyNews runtime Python. --baseline checks that the original
regressions reproduce using the committed HTML/client instead of working files.
"""
import argparse
import json
import mimetypes
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-10"
HTML = "内装製品デイリーニュース.html"
NEWS = [dict(id=f"jp{i}", country="jp", date=DAY, digestDate=DAY,
             title=f"並び替え検証 {i}", desc="この内容は検証用です", tags=[],
             img="", source="Fixture", url="https://example.invalid/",
             interiorScore=100-i) for i in range(1, 4)]
INSIGHTS = [dict(date=DAY, analysis={"jp": "検証用の考察"}, ideas={"jp": [
    dict(id=999999, title="検証用アイデア", desc="コメント欄を保護", img="")]} )]


def verify(browser, edition, width, baseline=False):
    context = browser.new_context(viewport={"width": width, "height": 1000},
                                  reduced_motion="reduce", service_workers="block")
    state = {n["id"]: dict(likes=0, comments=0, reads=0, liked=False, commentItems=[]) for n in NEWS}
    errors, held, posts = [], [], []
    control = {"hold": False, "fail": False}
    before = {}
    if baseline:
        for name in [HTML, "dailynews_client.js"]:
            before[name] = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=ROOT)

    def response(item, req):
        data = state.setdefault(item, dict(likes=0, comments=0, reads=0, liked=False, commentItems=[]))
        if req.method == "PUT" and req.url.split("?")[0].endswith("/like"):
            liked = req.post_data_json["liked"]
            data["likes"] += int(liked) - int(data["liked"])
            data["liked"] = liked
        if req.method == "POST" and req.url.split("?")[0].endswith("/comments"):
            data["commentItems"].append(dict(id=len(posts)+1, user="Fixture",
                                               text=req.post_data_json["text"], date=DAY, canDelete=True))
            data["comments"] = len(data["commentItems"])
        if req.method == "DELETE":
            comment_id = int(urlparse(req.url).path.rsplit("/", 1)[1])
            data["commentItems"] = [c for c in data["commentItems"] if c["id"] != comment_id]
            data["comments"] = len(data["commentItems"])
        return data

    def route(r):
        parsed = urlparse(r.request.url)
        if parsed.hostname != "dailynews.test":
            r.abort(); return
        path = unquote(parsed.path).removeprefix("/exterior").lstrip("/")
        name = path.rsplit("/", 1)[-1]
        if path == "api/interactions":
            r.fulfill(json={"interactions": state}); return
        if path.startswith("api/interactions/"):
            item = path.split("/")[2]
            if r.request.method == "POST" and name == "comments":
                posts.append(item)
                if control["hold"]:
                    held.append((r, item)); return
                if control["fail"]:
                    r.fulfill(status=503, json={"error": {"message": "fixture failure"}}); return
            r.fulfill(json=response(item, r.request)); return
        if path.startswith("api/"):
            r.fulfill(json={"total": 0, "daily": {}, "users": [], "activity": [],
                            "notifications": [], "unreadCount": 0, "favorites": [], "seenKeys": []}); return
        scripts = {
            "news_data.js": "window.LOADED_NEWS_DATA="+json.dumps(NEWS)+";",
            "insights_data.js": "window.DAILY_INSIGHTS="+json.dumps(INSIGHTS)+";",
            "dailynews_account.js": "window.dailyNewsAccount={user:{id:'fixture'}};",
            "release_history.js": "",  # History is checked separately against deployed assets.
        }
        if name in scripts:
            r.fulfill(body=scripts[name], content_type="application/javascript"); return
        if name == "publication_status.json":
            r.fulfill(json={"edition_id": "exterior", "status": "published", "processed_through": DAY,
                            "target_dates": [DAY], "selected_count": 3}); return
        file = ROOT/(path or HTML)
        if not file.resolve().is_relative_to(ROOT) or not file.is_file():
            r.fulfill(status=404); return
        r.fulfill(body=before.get(file.name, file.read_bytes()),
                  content_type=mimetypes.guess_type(file.name)[0] or "application/octet-stream")

    context.route("**/*", route)
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.goto("http://dailynews.test/"+("exterior/" if edition == "exterior" else "")
              +f"?from={DAY}&to={DAY}&new=0", wait_until="domcontentloaded")
    page.wait_for_function("window.firebaseInteractionsReady && document.querySelector('#card-jp3')")
    page.evaluate("NEW_DATE_RANGE={start:'2026-11-10',end:'2026-11-10'}; applyFilters()")

    def order():
        return page.locator("#newsGrid > .card").evaluate_all("els=>els.map(e=>e.dataset.newsId)")

    def like(item):
        page.evaluate("id=>toggleLike(id,document.querySelector('#card-'+id+' .action-btn[onclick*=toggleLike]'))", item)

    def open_editor(item="jp3"):
        card = page.locator("#card-"+item if item != "999999" else "#idea-card-999999")
        if not card.locator(".comment-section.open").count():
            card.locator(".btn-comment").click()
        return card.locator(".comment-input")

    def post(item, text):
        editor = open_editor(item)
        editor.fill(text)
        editor.evaluate("e=>window.savedEditor=e")
        page.evaluate("id=>submitComment(id,window.savedEditor)", item)
        return editor

    # Each original symptom is independently reproducible before the fix.
    symptoms = {}
    page.locator("#sortOrder").select_option("likes-desc")
    like("jp3")
    symptoms["like_reorders"] = order()[0] == "jp3"
    like("jp3")
    page.locator("#sortOrder").select_option("new-first")
    editor = post("jp3", "順位が変わるコメント")
    symptoms["comment_reorders"] = order()[0] == "jp3"
    if baseline:
        assert not any(symptoms.values()), symptoms
        context.close()
        return {"edition": edition, "width": width, "regressions_reproduced": list(symptoms)}
    assert all(symptoms.values()), symptoms
    assert editor.evaluate("e=>e===window.savedEditor && e===document.activeElement && e.value===''")
    assert page.locator("#card-jp3 .comment-section.open").count() == 1
    page.evaluate("document.activeElement.blur()")
    page.evaluate("deleteComment('jp3',0)")
    assert order() == ["jp1", "jp2", "jp3"], "comment deletion must restore order"
    assert editor.evaluate("e=>e===window.savedEditor"), "do not replace the input during sort"

    # Counts must sort in each relevant mode; unrelated sorts stay unchanged.
    page.locator("#sortOrder").select_option("comments-desc")
    post("jp2", "コメント数順でも即反映")
    assert order()[0] == "jp2"
    page.evaluate("document.activeElement.blur(); deleteComment('jp2',0)")
    assert order() == ["jp1", "jp2", "jp3"]
    page.locator("#sortOrder").select_option("likes-desc")
    open_editor("jp1")  # Merely opening a panel must not suppress sorting.
    page.evaluate("window.savedCard=document.getElementById('card-jp1'); window.savedIdea=document.getElementById('idea-card-999999')")
    like("jp3")
    assert order()[0] == "jp3"
    assert page.locator("#card-jp3 .action-btn.liked .count").inner_text() == "1"
    assert page.evaluate("savedCard===document.getElementById('card-jp1') && savedIdea===document.getElementById('idea-card-999999')")
    like("jp3")
    assert order() == ["jp1", "jp2", "jp3"]
    for sort in ["date-desc", "date-asc", "country", "relevance-desc"]:
        page.locator("#sortOrder").select_option(sort)
        like("jp3")
        assert order() == ["jp1", "jp2", "jp3"], sort
        like("jp3")

    # Draft, selection, focus and IME protection also applies to idea comments.
    page.locator("#sortOrder").select_option("new-first")
    for item in ["jp1", "999999"]:
        editor = open_editor(item)
        editor.fill("入力途中を保持")
        editor.evaluate("e=>{window.savedEditor=e;e.setSelectionRange(1,3);e.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));}")
        state["jp3"]["likes"] = 10
        page.evaluate("window.initDailyNewsApi()")  # The real polling callback, fixture data.
        assert order() == ["jp1", "jp2", "jp3"]
        assert editor.evaluate("e=>e===savedEditor && e===document.activeElement && e.selectionStart===1 && e.selectionEnd===3")
        count = len(posts)
        editor.dispatch_event("keypress", {"key": "Enter", "keyCode": 229, "isComposing": True})
        page.wait_for_timeout(180)
        assert len(posts) == count, "IME confirmation must not submit a comment"
        editor.evaluate("e=>e.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}))")
        editor.fill("")
        page.evaluate("document.activeElement.blur()")
        page.wait_for_function("document.querySelector('#newsGrid>.card').dataset.newsId==='jp3'")
        assert editor.evaluate("e=>e===savedEditor"), "deferred reorder must preserve nodes"
        state["jp3"]["likes"] = 0
        page.evaluate("window.initDailyNewsApi()")
        assert order() == ["jp1", "jp2", "jp3"]

    # Do not clear drafts or allow duplicate submissions while saving.
    editor = open_editor("jp3")
    editor.fill("送信する文章")
    control["hold"] = True
    page.evaluate("()=>{window.savedEditor=document.querySelector('#card-jp3 .comment-input'); window.savePromise=submitComment('jp3',savedEditor);}")
    page.wait_for_function("savedEditor.dataset.commentSubmitting==='true'")
    page.wait_for_timeout(50)
    assert held and editor.input_value() == "送信する文章"
    count = len(posts)
    page.evaluate("submitComment('jp3',savedEditor)")
    assert len(posts) == count, "duplicate submit"
    editor.fill("待機中に書いた次の文章")
    r, item = held.pop()
    control["hold"] = False
    r.fulfill(json=response(item, r.request))
    page.evaluate("window.savePromise")
    assert editor.input_value() == "待機中に書いた次の文章"
    assert order() == ["jp1", "jp2", "jp3"], "new draft must defer movement"
    editor.fill("")
    page.evaluate("document.activeElement.blur()")
    page.wait_for_function("document.querySelector('#newsGrid>.card').dataset.newsId==='jp3'")
    control["fail"] = True
    post("jp2", "失敗しても残る文章")
    assert page.locator("#card-jp2 .comment-input").input_value() == "失敗しても残る文章"
    control["fail"] = False
    page.locator("#card-jp2 .comment-input").fill("")
    page.evaluate("document.activeElement.blur()")

    # Full visibility changes remain deferred until readers close their panels.
    state["jp1"]["hidden"] = True
    page.evaluate("window.initDailyNewsApi()")
    assert page.locator("#card-jp1").count() == 1
    like("jp2")
    assert page.locator("#card-jp1").count() == 1, "reaction sort must not apply a deferred hide"
    page.evaluate("document.querySelectorAll('.comment-section.open').forEach(s=>s.classList.remove('open')); flushPendingNewsRefresh()")
    assert page.locator("#card-jp1").count() == 0
    assert not errors, errors
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), "horizontal overflow"
    context.close()
    return {"edition": edition, "width": width, "status": "PASS", "comment_requests": len(posts)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        results = [verify(browser, edition, width, args.baseline)
                   for edition in ["interior", "exterior"] for width in [1440, 390]]
        browser.close()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
