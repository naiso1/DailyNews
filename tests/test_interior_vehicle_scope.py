"""Real recurrence subjects and boundaries for the quota-independent bike gate."""
import unittest

from dailynews.interior_vehicle_scope import motorcycle_exclusion


class InteriorVehicleScopeTests(unittest.TestCase):
    def test_recent_published_motorcycle_subjects_are_excluded(self):
        cases = [
            ("ヤマハYZF-R1M、電子制御サスペンションとカーボンエアロ", "", ""),
            ("Royal Enfield Classic 350 Signature White Edition", "ブラウンシートとTripper Pod", ""),
            ("ホンダQC3、5インチTFTとRoadSync搭載", "Honda Motorcycle & Scooter Indiaは電動スクーターを発売。", ""),
            ("スズキGSX-S1000GT+、快適装備を更新", "スポーツバイクのシートを変更", ""),
            ("バジャジ、パルスAR NS400ZにTFTメーター採用へ", "", "https://example.test/bike-news/440839"),
            ("BMW R 1300 RTとGold Wing Tour DCTの内装装備", "シートヒーターとTFT", "https://example.test/touring-motorcycles-make-riding-easy/"),
            ("Bajaj Pulsar NS200に5インチTFT採用へ", "", ""),
            ("バジャジ・パルスAR NS125、新LCDメーター", "", ""),
            ("Bajaj Pulsar NS125新型、フルカラーTFTと新スイッチギア", "", ""),
            ("Ultraviolette Shockwave、新100Vアーキテクチャ", "Ultravioletteは電動バイクShockwaveを発売する。", ""),
        ]
        for title, desc, url in cases:
            with self.subTest(title=title):
                self.assertTrue(motorcycle_exclusion(dict(title=title, desc=desc, url=url)))

    def test_multilingual_lead_and_section_survive_neutral_translation(self):
        for body in ("This two-wheeler gains a TFT cluster.", "这是电动摩托车的新仪表盘。", "電動スクーターの収納を拡大した。"):
            with self.subTest(body=body):
                self.assertTrue(motorcycle_exclusion(dict(originalTitle="New model", originalDesc=body,
                                                        title="新型車にディスプレイ", desc="内装を更新した。")))
        self.assertTrue(motorcycle_exclusion(dict(title="新LCDメーター", url="https://example.test/bike-reviews/new-model")))

    def test_generated_car_application_cannot_override_original_bike(self):
        item = dict(originalTitle="New motorcycle TFT", originalDesc="The motorcycle gets a capacitive display.",
                    title="内装にも役立つディスプレイ", desc="乗用車のドアトリムへ静電容量センサーを応用する構造を開発した。")
        self.assertTrue(motorcycle_exclusion(item))
        item['originalDesc'] += " It could be adapted to passenger car door trim using capacitive sensors."
        self.assertTrue(motorcycle_exclusion(item))

    def test_motorcycle_instrument_panel_is_not_a_car_application(self):
        self.assertTrue(motorcycle_exclusion(dict(title="Motorcycle instrument panel",
                                                desc="A capacitive sensor was integrated into the instrument panel.")))
        self.assertTrue(motorcycle_exclusion(dict(title="ライディングブーツの防水素材を刷新")))

    def test_resumed_translation_with_missing_original_body_still_excludes_bike(self):
        item = dict(originalTitle="New display", originalDesc="", title="新型ディスプレイ",
                    desc="電動スクーターのメーターを更新した。")
        self.assertTrue(motorcycle_exclusion(item))

    def test_existing_scope_switch_requires_explicit_approval_to_disable(self):
        item = dict(title="New motorcycle TFT")
        rule = dict(key="exclude_non_passenger_vehicles", enabled=False, version=1, review_status="pending")
        self.assertTrue(motorcycle_exclusion(item, [rule]))
        self.assertEqual(motorcycle_exclusion(item, [dict(rule, review_status="approved")]), "")

    def test_car_cargo_materials_and_grounded_transfer_are_preserved(self):
        cases = [
            dict(title="バイクを積載できるミニバンの収納", desc="ミニバンの荷室に固定具を開発した。"),
            dict(title="SUV bicycle storage", desc="The car cabin has a bike rack."),
            dict(title="ドアトリムに静電容量センサー", desc="表皮越しの操作に対応。Other news: motorcycle sales."),
            dict(title="自動車レース用シートのNUGRAIN表皮材", desc="清掃性と触感を両立した。"),
            dict(title="二輪技術を自動車内装へ転用", desc="乗用車のドアトリムへ静電容量センサーを応用する構造を開発した。"),
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertEqual(motorcycle_exclusion(item), "")


if __name__ == '__main__':
    unittest.main()
