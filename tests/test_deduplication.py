import copy
import unittest

from dailynews.deduplication import (
    deduplicate_articles, normalize_article_url, recent_title_history, same_story,
)


def article(url, title, desc, *, day="2026-09-18", country="jp", **extra):
    return dict(url=url, title=title, desc=desc, date=day, country=country, **extra)


RECALL_A = article(
    "https://news.yahoo.co.jp/articles/638af31?source=rss",
    "ダイハツムーヴなど3車種、内装材の燃焼基準不適合でリコール",
    "ダイハツはムーヴとキャンバス、スバルステラ計1万91台をリコールした。"
    "2025年5月から8月に製作された車両で、シートカバーや前席ドアアームレストの内装材が燃焼試験基準に適合しないため交換する。",
)
RECALL_B = article(
    "https://response.jp/article/2026/09/19/416811.html",
    "ダイハツムーヴ等3車種、内装材燃焼基準不適合でリコール",
    "ダイハツは9月10日、ムーヴ・キャンバスとスバルステラ計1万91台のリコールを届出た。"
    "2025年5〜8月製車で、シートカバー等の表皮加工不備により燃焼試験基準を満たさないおそれがあるため交換する。",
    day="2026-09-19",
)
G9_A = article(
    "https://carnewschina.com/2026/09/18/xpeng-g9l-5-1-meter-suv-to-reach-global-market-at-the-paris-auto-show/",
    "XPeng G9Lがパリモーターショーでグローバル展開を宣言",
    "Xpengの大型SUV「G9L」は10月12日のパリモーターショーでグローバル展開を開始し、オーストリア工場で量産される。"
    "車体長5120mmの5人乗りモデルで、Huawei製ヘッドランプによる98インチ外部投影機能を備える。",
    country="cn",
)
G9_B = article(
    "https://www.automotiveworld.com/news/xpeng-g9l-set-for-october-launch-at-paris-motor-show/",
    "Xpeng G9L、パリモーターショーで世界初公開へ",
    "Xpengは10月12日のパリモーターショーでG9Lを国際展開する。欧州ではMagnaのグラーツ工場で生産し、VLA 2.0 AIモデルとTuring AIチップを搭載した。",
    country="eu",
)
KICKS_A = article(
    "https://www.motor1.com/news/808469/nissan-kicks-power-confirmed-europe/",
    "日産、サندرランドに170百万ポンド投資しKicks E-Powerを欧州へ投入",
    "日産は英国サドルランド工場への170百万ポンド（230百万米ドル）の投資を発表した。"
    "同工場で生産されるKicksは第3世代E-Powerハイブリッドシステムを搭載し、QashqaiやJukeとともに欧州市場で展開される。",
    day="2026-09-16", country="us",
)
KICKS_B = article(
    "https://www.autoexpress.co.uk/nissan/370445/nissan-kicks-new-life-sunderland-hybrid-suv-coming-uk",
    "日産Kicks、英国Sunderland工場でe-Powerハイブリッド生産へ",
    "日産は小型SUV「Kicks」の英国・欧州導入を正式発表し、Sunderland工場への1億7000万ポンド投資を発表した。"
    "2024年公開の2代目モデルで、英国仕様はe-Powerハイブリッド搭載が有力視されている。量産開始時期は未定。",
    day="2026-09-16", country="eu",
)
RENAULT_A = article(
    "https://www.autoexpress.co.uk/renault/370474/renaults-design-future-concept-car-new-rafale-and-new-scenic-aim-audacity",
    "ルノー新デザイン責任者が次期ラファールとシエニックに大胆な個性を追求",
    "ルノーの新デザイン責任者マルヴァル氏は、10月頃のパリでミッドサイズコンセプトカーを初披露する計画を明らかにした。"
    "次期ラファールやシエニックなどファミリー向けモデルに個性と大胆なプロポーションをもたらす狙いがある。",
    day="2026-09-19", country="eu",
)
RENAULT_B = article(
    "https://www.autoexpress.co.uk/renault/370473/renaults-design-future-pictures",
    "ルノー新デザイン責任者、大胆な個性とプロポーションを掲げる",
    "Auto Expressが2026年9月19日に掲載した記事で、ルノーの新ブランドデザイン責任者アレクサンドル・マルヴァル氏が、"
    "コンセプトカーや新型ラファール、シエニックを通じて大胆さと優れたプロポーションを備えたファミリーカーの提供を約束している。",
    day="2026-09-19", country="eu",
)


class UrlTests(unittest.TestCase):
    def test_tracking_removed_but_identity_and_page_retained(self):
        self.assertEqual(
            normalize_article_url("HTTPS://Example.COM/news?id=123&page=2&source=rss&utm_source=x&fbclid=a"),
            "https://example.com/news?id=123&page=2",
        )

    def test_unknown_parameters_fragments_and_duplicates_are_preserved(self):
        url = "https://example.com/a?id=1&id=2&source=dealer&lang=ja&empty=#chapter"
        self.assertEqual(normalize_article_url(url), url)
        self.assertNotEqual(normalize_article_url(url), normalize_article_url(url.replace("id=2", "id=3")))

    def test_id_differences_do_not_become_same_story(self):
        a = dict(G9_A, url="https://example.com/news?id=1")
        b = dict(G9_B, url="https://example.com/news?id=2")
        self.assertEqual(same_story(a, b), "")

    def test_tracking_only_url_match_does_not_require_translation_or_dates(self):
        self.assertEqual(same_story({"url": "https://example.com/a?utm_source=x"}, {"url": "https://example.com/a"}), "same_url")

    def test_empty_and_non_http_values(self):
        self.assertEqual(normalize_article_url(None), "")
        self.assertEqual(normalize_article_url("  relative/path?id=2  "), "relative/path?id=2")
        self.assertEqual(same_story({}, {}), "")


class StoryTests(unittest.TestCase):
    def test_identical_long_copy_matches_unregistered_company_and_model(self):
        body = ("新興企業アオバは新製品について詳細な技術資料を公開した。表面の光沢を抑える加工と複層構造を組み合わせ、"
                "試作条件ごとの測定結果を示している。資料では材料の調達条件や耐候試験の温度についても説明し、量産時期は未定としている。")
        a = article("https://first.test/a", "アオバ、新製品の技術資料を公開", body)
        b = article("https://second.test/b", a["title"], body)
        self.assertEqual(same_story(a, b), "identical_article_copy")

    def test_identical_syndicated_review_is_copy_not_an_independent_review(self):
        body = ("筆者は車両を市街地と郊外で試乗した。前席のクッションは柔らかく、長時間走行でも姿勢を保ちやすかったと評価する。"
                "一方で後席中央の床には段差があり、三人乗車時には足元の配置に注意が必要だったと報告している。価格や販売計画への評価は記載していない。")
        a = article("https://first.test/review", "MG Hector試乗レビュー", body)
        b = article("https://copy.test/review", a["title"], body)
        self.assertEqual(same_story(a, b), "identical_article_copy")

    def test_identical_short_snippet_is_not_enough_for_unknown_articles(self):
        a = article("https://first.test/a", "新製品の最新情報", "新しい製品を発表した。")
        b = article("https://second.test/b", a["title"], a["desc"])
        self.assertEqual(same_story(a, b), "")

    def test_audited_positive_pairs_in_both_directions(self):
        for a, b, reason in [
            (RECALL_A, RECALL_B, "same_recall_model_count_defect"),
            (G9_A, G9_B, "same_model_show_and_event_date"),
            (KICKS_A, KICKS_B, "same_model_production_investment"),
            (RENAULT_A, RENAULT_B, "article_picture_gallery"),
        ]:
            with self.subTest(reason=reason):
                self.assertEqual(same_story(a, b), reason)
                self.assertEqual(same_story(b, a), reason)

    def test_gias_and_stradia_are_distinct_products(self):
        a = article("https://example.com/1", "ブリッド、ヌグレ採用スーパーセミバケットシート発売",
                    "BRIDEはGIAS III NUGRAINを9月16日より受注開始した。")
        b = article("https://example.com/2", "ブリッド、ヌグレ表皮採用のシート発売",
                    "BRIDEはSTRADIA III NUGRAINを9月16日に発売した。")
        self.assertEqual(same_story(a, b), "")

    def test_distinct_mg_reviews_are_kept(self):
        a = article("https://autocarindia.com/review", "MG Hector Tomahawk EV、7人乗りと15.6インチHMIを備える",
                    "MGはADAPT採用Hectorを194.9万〜229.9万ルピーで展開。通気機能付きシートを備える。",
                    originalTitle="3 reasons to buy the MG Hector Tomahawk EV and 3 reasons not to")
        b = article("https://rushlane.com/review", "MG Hector Tomahawk EV、Dune Brown基調の内装と15.6インチ画面",
                    "MGはHectorを195万〜235万ルピーで展開。256色アンビエントライトを備える。",
                    originalTitle="MG Hector Tomahawk EV Review - Big On Space, Comfort And Features")
        self.assertEqual(same_story(a, b), "")
        # Even absent raw titles, common model/specification is not announcement identity.
        self.assertEqual(same_story({k: v for k, v in a.items() if k != "originalTitle"},
                                    {k: v for k, v in b.items() if k != "originalTitle"}), "")

    def test_new_price_specs_and_policy_followups_survive(self):
        for title in ("XPeng G9L、新仕様の詳細を公表", "XPeng G9L、価格を発表", "XPeng G9L、受注開始"):
            self.assertEqual(same_story(G9_A, dict(G9_B, title=title)), "")
        policy = dict(KICKS_B, desc=KICKS_B["desc"] + "ZEV規制が緩和されない限り実施を見送ると警告した。")
        self.assertEqual(same_story(KICKS_A, policy), "")

    def test_old_event_mentioned_as_background_does_not_swallow_new_feature(self):
        updated = dict(G9_B, title="XPeng G9Lのヘッドライトに投影機能を搭載")
        self.assertEqual(same_story(G9_A, updated), "")
        new_models = dict(KICKS_B, title="日産Kicksと新型Jukeを英国生産へ")
        self.assertEqual(same_story(KICKS_A, new_models), "")

    def test_conflicting_event_date_or_revised_investment_is_preserved(self):
        self.assertEqual(same_story(G9_A, dict(G9_B, desc=G9_B["desc"].replace("10月12日", "10月13日"))), "")
        revised = dict(KICKS_B, desc=KICKS_B["desc"] + "従来の1億7000万ポンドから2億ポンドへ投資を増額する。")
        self.assertEqual(same_story(KICKS_A, revised), "")

    def test_different_target_markets_are_not_merged(self):
        a = dict(G9_A, desc="Xpeng G9Lを10月12日のパリモーターショーで日本市場へ投入すると発表。")
        b = dict(G9_B, desc="Xpeng G9Lを10月12日のパリモーターショーで欧州市場へ投入すると発表。")
        self.assertEqual(same_story(a, b), "")

    def test_same_brand_show_date_different_model_survives(self):
        b = dict(G9_B, title=G9_B["title"].replace("G9L", "G6"), desc=G9_B["desc"].replace("G9L", "G6"))
        self.assertEqual(same_story(G9_A, b), "")

    def test_different_counts_defects_and_investment_survive(self):
        self.assertEqual(same_story(RECALL_A, dict(RECALL_B, desc=RECALL_B["desc"].replace("1万91", "1万501"))), "")
        self.assertEqual(same_story(RECALL_A, dict(RECALL_B, title="ダイハツムーヴのブレーキをリコール",
                                                  desc="ダイハツムーヴ計1万91台のブレーキ不具合をリコール。")), "")
        self.assertEqual(same_story(KICKS_A, dict(KICKS_B, desc=KICKS_B["desc"].replace("1億7000万", "2億"))), "")

    def test_same_model_without_explicit_event_facts_is_ambiguous(self):
        self.assertEqual(same_story(dict(G9_A, desc="Xpeng G9Lが新たな展開を予定する。"),
                                    dict(G9_B, desc="Xpeng G9Lに関する新情報を紹介。")), "")

    def test_gallery_requires_same_publisher_and_explicit_slug_relationship(self):
        self.assertEqual(same_story(RENAULT_A, dict(RENAULT_B, url=RENAULT_B["url"].replace("autoexpress.co.uk", "example.com"))), "")
        self.assertEqual(same_story(RENAULT_A, dict(RENAULT_B, url=RENAULT_B["url"].replace("design-future", "interior-materials"))), "")

    def test_unknown_dates_are_not_semantic_evidence(self):
        self.assertEqual(same_story(dict(G9_A, date=""), G9_B), "")

    def test_final_enriched_content_enables_recall_match(self):
        before = dict(RECALL_B, title="Daihatsu Move recall", desc="The company has announced a recall.")
        self.assertEqual(same_story(RECALL_A, before), "")
        self.assertTrue(same_story(RECALL_A, RECALL_B))


class PipelineTests(unittest.TestCase):
    def test_history_is_sorted_by_latest_date_not_file_tail(self):
        rows = [{"日付": "2026-09-20", "タイトル": "latest"},
                {"日付": "2025-12-29", "タイトル": "oldest"},
                {"date": "2026-09-19", "originalTitle": "previous"}]
        self.assertEqual(recent_title_history(rows, 2), ["latest", "previous"])
        self.assertEqual(recent_title_history(rows, 0), [])

    def test_history_titles_skip_empty_and_exact_repeats(self):
        self.assertEqual(recent_title_history([
            {"date": "2026-09-20", "title": "A"}, {"date": "2026-09-19", "title": "A"},
            {"date": "invalid", "title": "B"}, {"date": "2026-09-21", "title": ""},
        ]), ["A", "B"])

    def test_batch_consolidates_sources_and_does_not_mutate_inputs(self):
        candidates = [dict(G9_A, id="a", relatedUrls=["https://example.com/previous-source"]),
                      dict(G9_B, id="b", relatedUrls=["https://example.com/another-source"])]
        original = copy.deepcopy(candidates)
        kept, decisions = deduplicate_articles(candidates, issue_date="2026-09-20")
        self.assertEqual(candidates, original)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["id"], "a")
        self.assertEqual(kept[0]["relatedUrls"], ["https://example.com/previous-source", G9_B["url"], "https://example.com/another-source"])
        self.assertEqual(decisions, [{"url": G9_B["url"], "duplicate_of": G9_A["url"],
                                    "reason": "same_model_show_and_event_date", "kind": "batch"}])

    def test_duplicate_url_within_batch_is_removed_even_with_tracking(self):
        kept, decisions = deduplicate_articles([G9_A, dict(G9_A, url=G9_A["url"] + "?utm_source=rss")])
        self.assertEqual(len(kept), 1)
        self.assertEqual(decisions[0]["reason"], "same_url")
        self.assertNotIn("relatedUrls", kept[0])

    def test_history_window_inclusive_no_future_or_undated_history(self):
        for hist_day, rejected in [("2026-09-07", True), ("2026-09-06", False),
                                   ("2026-09-21", True), ("2026-09-22", False), ("", False)]:
            with self.subTest(hist_day=hist_day):
                kept, decisions = deduplicate_articles([G9_A], [dict(G9_A, date=hist_day)], issue_date="2026-09-21")
                self.assertEqual(not kept, rejected)
                if rejected:
                    self.assertEqual(decisions[0]["kind"], "history")

    def test_recent_semantic_history_and_related_url_identity(self):
        kept, decisions = deduplicate_articles([G9_B], [G9_A], issue_date="2026-09-20")
        self.assertFalse(kept)
        self.assertEqual(decisions[0]["duplicate_of"], G9_A["url"])
        kept, decisions = deduplicate_articles([dict(G9_B, title="", desc="")],
                                               [dict(G9_A, relatedUrls=[G9_B["url"]])], issue_date="2026-09-20")
        self.assertFalse(kept)
        self.assertEqual(decisions[0]["reason"], "same_url")

    def test_protected_replay_keeps_id_and_collects_nonprotected_duplicates(self):
        protected = dict(G9_B, id="published")
        kept, decisions = deduplicate_articles([G9_A, protected], [G9_A, protected],
                                               issue_date="2026-09-20", protected_urls=[G9_B["url"]])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["id"], "published")
        self.assertEqual(kept[0]["relatedUrls"], [G9_A["url"]])
        self.assertEqual(decisions[0]["kind"], "batch")

    def test_two_protected_existing_ids_are_not_removed(self):
        kept, decisions = deduplicate_articles([G9_A, G9_B], [G9_A, G9_B],
                                               protected_urls=[G9_A["url"], G9_B["url"]])
        self.assertEqual(kept, [G9_A, G9_B])
        self.assertEqual(decisions, [])

    def test_repeated_protected_primary_url_is_consolidated_with_related_sources(self):
        a = dict(G9_A, id="first", relatedUrls=["https://example.com/first-source"])
        b = dict(G9_A, id="repeated", url=G9_A["url"] + "?utm_source=rss",
                 relatedUrls=["https://example.com/second-source"])
        before = copy.deepcopy([a, b])
        kept, decisions = deduplicate_articles([a, b], [G9_A], protected_urls=[G9_A["url"]])
        self.assertEqual([a, b], before)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["id"], "first")
        self.assertEqual(kept[0]["relatedUrls"], ["https://example.com/first-source", "https://example.com/second-source"])
        self.assertEqual(decisions[0]["reason"], "same_url")

    def test_no_date_disables_history_and_invalid_explicit_date_rejected(self):
        candidate = dict(G9_A, date="")
        self.assertEqual(deduplicate_articles([candidate], [G9_A])[0], [candidate])
        with self.assertRaises(ValueError):
            deduplicate_articles([G9_A], issue_date="bad")
        with self.assertRaises(ValueError):
            deduplicate_articles([G9_A], history_days=-1)


if __name__ == "__main__":
    unittest.main()
