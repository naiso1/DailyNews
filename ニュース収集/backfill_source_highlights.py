"""Add verified source links to one published date, without regenerating content."""

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from source_highlights import FIELDS, enrich_items, make_session

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "news_data.js"


def read_news(path=NEWS_PATH):
    code = """
const fs = require('fs'), vm = require('vm');
const context = {window: {}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context, {timeout: 5000});
process.stdout.write(JSON.stringify(context.window.LOADED_NEWS_DATA));
"""
    return json.loads(subprocess.check_output(["node", "-e", code, str(path)], encoding="utf-8"))


def add_highlight_fields(text, items):
    for item in items:
        if not item.get("sourceExcerpt"):
            continue
        pattern = re.compile(r'(?m)^([ \t]*)id: "' + re.escape(item["id"]) + r'",(\r?\n)')
        matches = list(pattern.finditer(text))
        if len(matches) != 1:
            raise ValueError(f"Expected one news object for {item['id']}")
        match = matches[0]
        addition = "".join(match[1] + f + ": " + json.dumps(item[f], ensure_ascii=False) + "," + match[2]
                           for f in FIELDS if item.get(f))
        text = text[:match.end()] + addition + text[match.end():]
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Article date, not the pipeline execution date (YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Write verified links; default only checks and reports")
    parser.add_argument("--windows-proxy", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    datetime.strptime(args.date, "%Y-%m-%d")
    original = NEWS_PATH.read_bytes()
    news = read_news()
    selected = [item for item in news if item.get("date") == args.date]
    if not selected:
        raise ValueError("No articles for this date; nothing changed")
    missing = [item for item in selected if not item.get("sourceExcerpt")]
    print(f"Selected {len(selected)} articles ({len(missing)} without source links)", flush=True)
    with make_session(args.windows_proxy) as session:
        report = enrich_items(missing, session=session)
    output = {"date": args.date, "selected": len(selected), "results": report}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.apply:
        updated = add_highlight_fields(original.decode("utf-8"), missing)
        if NEWS_PATH.read_bytes() != original:
            raise RuntimeError("news_data.js changed during verification; refusing to overwrite")
        temporary = NEWS_PATH.with_suffix(".js.tmp")
        temporary.write_bytes(updated.encode("utf-8"))
        # Parse the result and prove every existing content field is unchanged.
        checked = read_news(temporary)
        for before, after in zip(news, checked, strict=True):
            for field, value in before.items():
                if after.get(field) != value:
                    raise RuntimeError(f"Unexpected change: {before.get('id')}.{field}")
        os.replace(temporary, NEWS_PATH)
    print(json.dumps(Counter(row["status"] for row in report), ensure_ascii=False))
    print(f"{'Applied' if args.apply else 'Checked only'}; report: {args.report}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
