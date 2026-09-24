import unittest

from dailynews.exterior import selection_thresholds


class IssueDayThresholdTests(unittest.TestCase):
    selection = {"minimum_score": 60, "trend_minimum_score": 65,
                 "issue_date_minimum_score": 45, "issue_date_trend_minimum_score": 45}

    def test_issue_day_is_relaxed_and_lookback_days_keep_strict_scores(self):
        self.assertEqual(selection_thresholds(self.selection, "2026-09-23", "2026-09-23"), (45, 45))
        self.assertEqual(selection_thresholds(self.selection, "2026-09-23 08:00", "2026-09-23"), (45, 45))
        self.assertEqual(selection_thresholds(self.selection, "2026-09-22", "2026-09-23"), (60, 65))

    def test_without_issue_settings_or_issue_day_the_base_scores_apply(self):
        base = {"minimum_score": 60, "trend_minimum_score": 65}
        self.assertEqual(selection_thresholds(base, "2026-09-23", "2026-09-23"), (60, 65))
        self.assertEqual(selection_thresholds(self.selection, "2026-09-23", ""), (60, 65))


if __name__ == "__main__":
    unittest.main()
