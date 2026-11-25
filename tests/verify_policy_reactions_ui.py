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
    page.route("https://cdn.motor1.com/**", lambda route: route.fulfill(
        content_type="image/webp", path=ROOT / "page_images/policy_cover.webp"))
    page.goto(base + "/?countries=policy")
    expect(page.locator("#policyHighlightResults article")).to_have_count(5)
    expect(page.locator("#policyResults article")).to_have_count(3)
    page.locator(".release-history-confirm").click()
    expect(page.locator("#policyChip .policy-icon")).to_be_visible()
    expect(page.locator("#policyResults .new-badge")).to_have_count(3)
    expect(page.locator("#policyHighlightResults .new-badge")).to_have_count(0)
    daily = page.locator("#policyResults article").first
    daily_id = daily.get_attribute("data-news-id")
    photo = page.locator("#policyResults article").nth(1)
    photo.scroll_into_view_if_needed()
    expect(photo.locator(".thumb img")).to_have_js_property("naturalWidth", 768)
    expect(photo.locator(".policy-photo-credit")).to_be_visible()
    first = page.locator("#policyHighlightResults article").first
    first.scroll_into_view_if_needed()
    expect(first.locator(".thumb img")).to_have_attribute("src", "page_images/policy_cover.webp")
    expect(first.locator(".thumb img")).to_have_js_property("naturalWidth", 768)
    expect(first.locator(".policy-photo-credit")).to_have_count(0)
    item_id = first.get_attribute("data-news-id")
    for card in page.locator(".policy-story").all():
        for selector in (".btn", ".card-tag", ".favorite-btn", ".article-copilot-btn", ".article-settings-btn",
                         ".read-count", ".source", ".card-date-meta", ".id-badge"):
            expect(card.locator(selector).first).to_be_visible()
        expect(card.locator(".id-badge")).to_have_text(card.get_attribute("data-news-id"))
    tag = first.locator(".card-tag").first
    tag_name = tag.inner_text()
    tag.click()
    expect(page.locator("#searchInput")).to_have_value(tag_name)
    expect(page.locator(f"#card-{item_id}")).to_be_visible()
    page.goto(base + "/?countries=policy")
    with page.expect_response(lambda r: r.url.endswith("/favorites/" + item_id) and r.status == 200):
        first.locator(".favorite-btn").click()
    page.reload()
    expect(first.locator(".fav-icon")).to_have_text("★")
    page.locator("#favoritesToggle").click()
    expect(page.locator(".policy-story")).to_have_count(1)
    page.locator('#countryFilters .chip[data-country="world"]').click()
    expect(page.locator(f"#newsGrid #card-{item_id} .favorite-select")).to_be_visible()
    page.goto(base + "/?countries=policy")
    first.locator(".article-copilot-btn").click()
    expect(page.locator(".dncp-current-article")).to_contain_text(first.locator(".title").inner_text())
    expect(page.locator("#companion-card-" + item_id)).to_have_count(1)
    page.get_by_role("button", name="会話を最小化").click()
    first.locator(".article-settings-btn").click()
    page.get_by_role("button", name="一覧から削除…").click()
    expect(page.locator("#articleRemovalItemTitle")).to_have_text(first.locator(".title").inner_text())
    page.locator(".article-removal-cancel").click()
    first.locator(".article-settings-btn").click()
    page.get_by_role("button", name="画像を変更").click()
    expect(page.locator("#imageEditorItemTitle")).to_have_text(first.locator(".title").inner_text())
    replacement = "https://cdn.motor1.com/test.jpg"
    page.locator("#imageEditorUrl").fill(replacement)
    page.locator(".image-editor-save").click()
    expect(first.locator(".thumb img")).to_have_attribute("src", replacement)
    expect(first.locator(".policy-photo-credit")).to_have_count(0)
    first.locator(".article-settings-btn").click()
    page.get_by_role("button", name="画像を変更").click()
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator(".image-editor-reset").click()
    expect(first.locator(".thumb img")).to_have_attribute("src", "page_images/policy_cover.webp")
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
    with page.expect_response(lambda r: r.url.endswith(f"/{daily_id}/like") and r.request.method == "PUT"):
        daily.locator('button[onclick*="toggleLike"]').click()
    rank = page.locator("#rankingList")
    historical_rank = rank.locator(f'[data-news-id="{item_id}"]')
    expect(rank.locator(f'[data-news-id="{daily_id}"]')).to_contain_text("法規・政策")
    expect(historical_rank).to_have_count(0)
    page.locator('#countryFilters .chip[data-country="world"]').click()
    page.locator("#rankingScope").select_option("all")
    expect(historical_rank.locator(".btn-comment .count")).to_have_text("2")
    expect(historical_rank.locator("button").first.locator(".count")).to_have_text("1")
    historical_rank.locator(".btn-comment").click()
    expect(page.locator(f'#card-{item_id} .comment-section')).to_be_visible()
    expect(page.locator(f'#card-{item_id} .reply-comment')).to_contain_text("設計チームで確認します。")
    page.locator('#countryFilters .chip[data-country="world"]').click()
    page.locator(f'#activityGrid [data-activity-item="{item_id}"]').first.click()
    expect(page.locator(".policy-story")).to_have_count(1)
    expect(page.locator(".policy-story")).to_have_attribute("data-news-id", item_id)
    page.reload()
    expect(page.locator(".policy-story")).to_have_count(1)
    for width in (390, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        box = page.locator(".policy-story").bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1
        page.locator("#releaseHistoryButton").evaluate("el => el.click()")
        overlay = page.locator("#releaseHistoryOverlay")
        expect(overlay).to_be_visible()
        expect(overlay.locator(".release-history-list")).to_contain_text("過去の注目法規")
        expect(overlay.locator(".release-history-entry").first).to_contain_text("人気ニュースランキング")
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
        (release / "page_images").mkdir()
        for filename in ("icon_policy.png", "policy_cover.webp"):
            shutil.copyfile(ROOT / "page_images" / filename, release / "page_images" / filename)
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
    print("PASS: daily and archived card controls, favorites, tags, article context, image override/reset, reactions, navigation and responsive history")


if __name__ == "__main__":
    main()
