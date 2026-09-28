"""Isolated browser regression: actual HTML/client, fixture API only, no live writes."""

import argparse
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-28"
IMAGE = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='90'%3E%3Crect width='160' height='90' fill='%23344750'/%3E%3C/svg%3E"
NEWS = [dict(id=f"{country}-{key}", country=country, date=DAY, issueDate=DAY,
             title=f"{key} 検証記事", desc="テスト用の概要", tags=[], img=IMAGE,
             source="Fixture", url="https://example.invalid/", isNew=True)
        for country in ["jp", "paper"] for key in ["views", "like", "comment", "idle"]]
INSIGHTS = [dict(date=DAY, analysis={"jp": "検証用の考察"}, ideas={"jp": [
    dict(id=999999, title="検証用のアイデア", desc="入力保護の確認", img=IMAGE)]})]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def translate_path(self, path):
        return super().translate_path(path.removeprefix("/exterior"))


def verify(browser, base, edition, width, artifacts):
    context = browser.new_context(viewport={"width": width, "height": 1000})
    interactions = {n["id"]: dict(likes=int(n["id"].endswith("-like")),
                                  comments=int(n["id"].endswith("-comment")),
                                  reads=10000 if n["id"].endswith("-views") else 0)
                    for n in NEWS}
    writes = []
    polls = []
    fail_post = False

    def route_request(route):
        req = route.request
        parsed = urlparse(req.url)
        if parsed.hostname != urlparse(base).hostname:
            route.abort()
            return
        path = unquote(parsed.path).removeprefix("/exterior")
        name = path.rsplit("/", 1)[-1]
        if "/api/" in path:
            api = path.split("/api/", 1)[1]
            if req.method != "GET":
                writes.append((req.method, api))
            if api == "interactions":
                polls.append(1)
                data = {"interactions": interactions}
            elif api.startswith("interactions/"):
                item_id = api.split("/")[1]
                data = interactions.setdefault(item_id, {"likes": 0, "comments": 0, "reads": 0})
                if api.endswith("/comments") and req.method == "POST":
                    if fail_post:
                        route.fulfill(status=503, json={"error": {"message": "fixture failure"}})
                        return
                    data["comments"] += 1
                    data["commentItems"] = [{"id": 1, "user": "Test", "text": req.post_data_json["text"]}]
            else:
                data = {"activity": [], "notifications": [], "unreadCount": 0, "users": []}
            route.fulfill(json=data)
        elif name == "news_data.js":
            route.fulfill(body="window.LOADED_NEWS_DATA=" + json.dumps(NEWS) + ";", content_type="application/javascript")
        elif name == "insights_data.js":
            route.fulfill(body="window.DAILY_INSIGHTS=" + json.dumps(INSIGHTS) + ";", content_type="application/javascript")
        elif name == "publication_status.js":
            route.fulfill(body="", content_type="application/javascript")
        elif name == "dailynews_account.js":
            route.fulfill(body="window.dailyNewsAccount={user:{id:'fixture'}};", content_type="application/javascript")
        else:
            assert req.method == "GET", req.url
            route.continue_()

    context.route("**/*", route_request)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.dismiss())
    page.goto(base.rstrip("/") + ("/exterior/" if edition == "exterior" else "/")
              + "内装製品デイリーニュース.html?from=" + DAY + "&to=" + DAY + "&new=0",
              wait_until="domcontentloaded")
    page.wait_for_function("window.firebaseInteractionsReady && document.querySelector('#card-jp-idle')")
    page.wait_for_function("document.querySelector('#rankingList .ranking-item')?.dataset.newsId === 'jp-comment'")
    assert page.locator("#rankingSort option:checked").inner_text() == "総合（反応重視）"
    assert page.locator("#paperRankingList .ranking-item").first.get_attribute("data-news-id") == "paper-comment"
    page.locator("#rankingSort").select_option("reads")
    page.wait_for_function("document.querySelector('#rankingList .ranking-item')?.dataset.newsId === 'jp-views'")
    page.locator("#rankingSort").select_option("score")

    for card_id, sort in [("card-jp-idle", "new-first"), ("card-jp-idle", "date-desc"), ("idea-card-999999", "new-first")]:
        page.locator("#sortOrder").select_option(sort)
        card = page.locator("#" + card_id)
        card.locator(".btn-comment").click()
        editor = card.locator(".comment-input")
        editor.fill("入力途中の文章を保持する")
        editor.evaluate("el => {window.testEditor=el;el.setSelectionRange(2,6);el.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true,data:'にゅうりょく'}));}")
        interactions["jp-like"]["likes"] += 1
        interactions["sync-marker"] = {"likes": interactions.get("sync-marker", {}).get("likes", 0) + 1}
        # Exercise a real 15-second poll once; invoke the same API sync for
        # the remaining viewport/edition cases to keep the test fast.
        if edition == "interior" and width == 1400 and card_id == "card-jp-idle" and sort == "new-first":
            page.wait_for_function("likes => window.interactionsData['sync-marker']?.likes === likes",
                                   arg=interactions["sync-marker"]["likes"], timeout=20000)
        else:
            page.evaluate("window.initDailyNewsApi()")
        assert card.locator(".comment-section").evaluate("el => el.classList.contains('open')"), "sync closed an active editor"
        assert editor.input_value() == "入力途中の文章を保持する", "sync discarded the draft"
        assert editor.evaluate("el => el === window.testEditor && el === document.activeElement && el.selectionStart === 2 && el.selectionEnd === 6"), "sync replaced or blurred the input"
        editor.evaluate("el => el.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'入力'}))")
        assert page.locator("#card-jp-like .action-btn[onclick*=toggleLike] .count").inner_text() == str(interactions["jp-like"]["likes"])

        # Closing a panel containing a draft must not make a pending refresh
        # discard the text. Posting failures must also retain it.
        card.locator(".btn-comment").click()
        assert editor.input_value() == "入力途中の文章を保持する"
        card.locator(".btn-comment").click()
        fail_post = True
        page.evaluate("(id) => submitComment(id, window.testEditor)", "999999" if card_id.startswith("idea-") else "jp-idle")
        assert editor.input_value() == "入力途中の文章を保持する"
        fail_post = False
        card.locator(".comment-submit").click()
        page.wait_for_function("window.testEditor.value === ''")
        # Wait for the response too; the current UI clears the field on send.
        page.wait_for_function("id => document.querySelector('#' + id + ' .comment-list .comment-item')", arg=card_id)
        assert card.locator(".comment-section.open").count() == 1
        card.locator(".btn-comment").click()
        assert editor.evaluate("el => el !== window.testEditor"), "pending refresh was not applied after editing ended"

    # Visibility changes follow the same protection, then apply on close.
    card = page.locator("#card-jp-idle")
    card.locator(".btn-comment").click()
    interactions["jp-views"]["hidden"] = True
    page.evaluate("window.initDailyNewsApi()")
    assert page.locator("#card-jp-views").count() == 1
    card.locator(".btn-comment").click()
    assert page.locator("#card-jp-views").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "horizontal overflow"
    assert not errors, errors
    if artifacts:
        artifacts.mkdir(parents=True, exist_ok=True)
        page.locator("#rankingSection").screenshot(path=str(artifacts / f"ranking-{edition}-{width}.png"))
    assert any(method == "POST" and path.endswith("/comments") for method, path in writes)
    print(f"PASS {edition} {width}px: scores, sorts, news/idea drafts+focus, composition, send/retry, deferred visibility ({len(polls)} syncs)")
    context.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--base", help="Optional deployed base URL; all APIs and protected content remain fixtures")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge")
            for edition in ["interior", "exterior"]:
                for width in [1400, 390]:
                    verify(browser, args.base or f"http://127.0.0.1:{server.server_port}", edition, width, args.artifacts)
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
