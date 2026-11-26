"""Build one edition's policy issue without consuming regional publication slots."""
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
    parser.add_argument("--edition", choices=("interior", "exterior"))
    args = parser.parse_args()
    edition = get_edition(args.edition)
    target = edition.content_dir / "policy_data.js"
    issues = policy.read_issues(target)
    days = sorted({date.fromisoformat(d).isoformat() for d in args.dates.split(",")})
    issue = days[-1]
    if issue in issues:
        return 0

    import google_search_script as collector

    collector.configure_edition(edition.id)
    rows = []
    with (edition.runtime_dir / "search_results.csv").open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row["日付"] in days and row.get("国") != "論文":
                rows.append(row)
    try:
        queries = policy.EXTERIOR_QUERIES if edition.id == "exterior" else policy.QUERIES
        rows.extend(collector.fetch_from_bing_search(days, policy_queries=queries))
    except RuntimeError as exc:
        print(f"[POLICY] {exc}。同日の通常収集結果から根拠を確認します。")
        if not rows:
            raise
    candidates = policy.shortlist(rows, edition.id)
    sources = policy.collect_evidence(candidates, collector.fetch_article_text)
    if candidates and not sources:
        raise ValueError("該当候補の本文を確認できません")
    def ask(prompt):
        answer = collector.call_llm_text(prompt, system_prompt=policy.EDITOR_INSTRUCTIONS)
        return collector.extract_json_object(answer)

    cards = policy.select_cards(sources, ask, edition.id)
    policy.add_source_images(cards, rows, collector.is_suspicious_image_url, collector.fetch_image_from_page)
    policy.save_issue(target, issue, cards, edition.id)
    print(f"[POLICY] {issue}: 確認候補{len(candidates)}件、掲載{len(cards)}件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
