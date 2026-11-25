"""Build the interior policy issue without consuming regional publication slots."""
import argparse
import csv
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dailynews.editions import get_edition
from dailynews import regulatory_news as policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates", required=True)
    args = parser.parse_args()
    edition = get_edition()
    if edition.id != "interior":
        parser.error("この欄は内装版専用です")
    target = edition.content_dir / "policy_data.js"
    issues = policy.read_issues(target)
    days = sorted({date.fromisoformat(d).isoformat() for d in args.dates.split(",")})
    issue = days[-1]
    if issue in issues:
        return 0

    import google_search_script as collector

    collector.configure_edition("interior")
    rows = []
    with (edition.runtime_dir / "search_results.csv").open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row["日付"] in days and row.get("国") != "論文":
                rows.append(row)
    try:
        rows.extend(collector.fetch_from_bing_search(days, policy_queries=policy.QUERIES))
    except RuntimeError as exc:
        print(f"[POLICY] {exc}。同日の通常収集結果から根拠を確認します。")
        if not rows:
            raise
    candidates = policy.shortlist(rows)
    sources = policy.collect_evidence(candidates, collector.fetch_article_text)
    if candidates and not sources:
        raise ValueError("該当候補の本文を確認できません")
    def ask(prompt):
        answer = collector.call_llm_text(prompt, system_prompt=policy.EDITOR_INSTRUCTIONS)
        return collector.extract_json_object(answer)

    cards = policy.select_cards(sources, ask)
    policy.add_source_images(cards, rows, collector.is_suspicious_image_url, collector.fetch_image_from_page)
    policy.save_issue(target, issue, cards)
    print(f"[POLICY] {issue}: 確認候補{len(candidates)}件、掲載{len(cards)}件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
