import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fx = load("exchange", ROOT / "update_exchange_rates.py")
grounding = load("grounding", ROOT / "ニュース収集" / "summary_grounding.py")
XML = b'<Envelope><Cube><Cube time="2026-09-07"><Cube currency="JPY" rate="180"/><Cube currency="USD" rate="1.2"/><Cube currency="INR" rate="100"/><Cube currency="CNY" rate="8"/><Cube currency="GBP" rate="0.85"/></Cube></Cube></Envelope>'


class ExchangeTests(unittest.TestCase):
    def test_cross_rates_and_dates(self):
        rates = fx.parse_rates(XML, dt.date(2026, 9, 8))
        self.assertEqual(rates["rates"]["USD"], 150)
        self.assertEqual(rates["rates"]["INR"], 1.8)
        self.assertEqual(rates["rates"]["EUR"], 180)
        for date in [dt.date(2026, 9, 6), dt.date(2026, 10, 1)]:
            with self.assertRaises(ValueError):
                fx.parse_rates(XML, date)
        for invalid in [b'0', b'NaN', b'-1', b'Infinity']:
            with self.assertRaises(ValueError):
                fx.parse_rates(XML.replace(b'"180"', b'"' + invalid + b'"'), dt.date(2026, 9, 8))

    def test_failed_fetch_preserves_snapshot_and_skips_same_day(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rates.js"
            import json
            snapshot = fx.parse_rates(XML, dt.date(2026, 9, 8))
            snapshot['checkedOn'] = dt.date.today().isoformat()
            original = fx.PREFIX + json.dumps(snapshot) + ';\n'
            path.write_text(original, encoding='utf-8')
            with patch.object(fx.urllib.request, 'build_opener') as opener:
                fx.update_rates(path)
                opener.assert_not_called()
                opener.return_value.open.side_effect = TimeoutError()
                fx.update_rates(path, force=True)
                self.assertEqual(path.read_text(encoding='utf-8'), original)

    def test_equipment_criticism_is_not_an_adoption_claim(self):
        source = 'センターテーブルやスイッチ類、室内灯にも、エルグランドにはこだわりが欲しかったようには思う。'
        self.assertTrue(grounding.reverses_equipment_criticism('センターテーブルやスイッチ類など、こだわりが備わる。', source))
        self.assertFalse(grounding.reverses_equipment_criticism('筆者はスイッチ類には改善の余地があると指摘。', source))
        self.assertFalse(grounding.reverses_equipment_criticism('菱形ステッチを採用する。', source))
        self.assertFalse(grounding.reverses_equipment_criticism('スイッチ類を採用する。', 'スイッチ類を採用する。'))


if __name__ == '__main__':
    unittest.main()
