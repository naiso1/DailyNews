"""Exercise policy threads against a disposable, loopback-only DailyNews database."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def check(browser, base):
    ctx = browser.new_context(viewport={"width": 1440, "height": 950})
    response = ctx.request.post(base + "/api/auth/register", headers={"Origin": base}, data={
        "email": "policy.reader@example.com", "displayName": "検証用",
        "password": "policy-test-only-4827", "clientId": "policyfixtureclient1234",
    })
    assert response.ok, response.status
    page = ctx.new_page()
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/") else route.abort())
    page.goto(base + "/?countries=policy")
    expect(page.locator("#policyHighlightResults article")).to_have_count(5)
    expect(page.locator("#policyResults article")).to_have_count(3)
    page.locator(".release-history-confirm").click()
    first = page.locator("#policyHighlightResults article").first
    item_id = first.get_attribute("data-news-id")
    like = first.locator('button[onclick*="toggleLike"]')
    with page.expect_response(lambda r: r.url.endswith(f"/{item_id}/like") and r.request.method == "PUT"):
        like.click()
    first.locator(".btn-comment").click()
    first.locator(".comment-input").fill("シート仕様への影響を確認します。")
    first.locator(".comment-submit").click()
    expect(first.locator(".comment-text")).to_have_text("シート仕様への影響を確認します。")
    first.locator(".comment-like-btn").click()
    expect(first.locator(".comment-like-btn")).to_contain_text("1")
    page.once("dialog", lambda dialog: dialog.accept("設計チームで確認します。"))
    first.locator(".comment-reply-btn").click()
    expect(first.locator(".reply-comment")).to_contain_text("設計チームで確認します。")
    page.reload()
    expect(like.locator(".count")).to_have_text("1")
    first.locator(".btn-comment").click()
    expect(first.locator(".comment-item")).to_have_count(2)
    expect(page.locator("#policyHighlightResults article").nth(1).locator(".btn-comment .count")).to_have_text("0")
    expect(page.locator("#policyResults article").first.locator(".btn-comment .count")).to_have_text("0")
    page.locator('#countryFilters .chip[data-country="world"]').click()
    page.locator(f'#activityGrid [data-activity-item="{item_id}"]').first.click()
    expect(page.locator(".policy-story")).to_have_count(1)
    expect(page.locator(".policy-story")).to_have_attribute("data-news-id", item_id)
    page.reload()
    expect(page.locator(".policy-story")).to_have_count(1)
    for width in (390, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        page.locator("#releaseHistoryButton").evaluate("el => el.click()")
        overlay = page.locator("#releaseHistoryOverlay")
        expect(overlay).to_be_visible()
        expect(overlay.locator(".release-history-list")).to_contain_text("過去の注目法規")
        expect(overlay.locator(".release-history-list")).to_contain_text("2026-11-25")
        assert overlay.evaluate("el => el.scrollWidth <= el.clientWidth")
        overlay.locator(".release-history-confirm").click()
    ctx.close()


def main():
    with tempfile.TemporaryDirectory(prefix="dailynews-policy-") as temp:
        root = Path(temp)
        release = root / "releases" / "abcdef1"
        release.mkdir(parents=True)
        (root / "active-release.txt").write_text("abcdef1", encoding="ascii")
        for pattern in ("dailynews_*.js", "dailynews_*.css", "policy_*.js", "release_history.js"):
            for asset in ROOT.glob(pattern):
                shutil.copyfile(asset, release / asset.name)
        shutil.copyfile(ROOT / "内装製品デイリーニュース.html", release / "index.html")
        (release / "news_data.js").write_text(
            'window.LOADED_NEWS_DATA=[{id:"jp1",country:"jp",title:"記事",desc:"確認",date:"2026-11-24",tags:[],isNew:true}];',
            encoding="utf-8")
        (release / "insights_data.js").write_text("window.DAILY_INSIGHTS=[];", encoding="ascii")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {k: v for k, v in os.environ.items() if not k.startswith("DAILYNEWS_")}
        env.update(DAILYNEWS_ROOT=str(root), DAILYNEWS_HOST="127.0.0.1", DAILYNEWS_PORT=str(port))
        server = subprocess.Popen(["node", str(ROOT / "deployment/windows-server/server.js")], env=env)
        try:
            for _ in range(50):
                try:
                    with urlopen(base + "/health", timeout=1):
                        break
                except OSError:
                    time.sleep(.1)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="msedge")
                check(browser, base)
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)
    print("PASS: 5 highlights, daily and retrospective threads, persistent likes/replies, navigation and history at both widths")


if __name__ == "__main__":
    main()
