"""Private, read-only synchronization of reviewed editorial settings.

Feedback prose, names and account/session data never enter this snapshot. Only
known approved switches and URLs of currently hidden articles reach selection.
"""
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

from dailynews.collection_digest import published_news
from dailynews.deduplication import normalize_article_url

POLICY_KEYS = frozenset({
    "exclude_non_passenger_vehicles", "exclude_off_topic",
    "seat_requires_transferable_value", "interior_lighting_only", "require_development_value",
})


def snapshot_path(context):
    if context.id not in {"interior", "exterior"}:
        raise ValueError("Unknown edition")
    return context.root / "runtime" / context.id / "editorial_feedback_policy.json"


def safe_url(value):
    try:
        parts = urlsplit(value) if isinstance(value, str) else None
        if parts and parts.scheme.lower() in {"http", "https"} and parts.hostname and not parts.username and not parts.password:
            return normalize_article_url(value)
    except ValueError:
        pass
    return ""


def _time(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Snapshot time must include a zone")
    return parsed.astimezone(timezone.utc)


def _validated(data, edition, now, max_age_days):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("edition") != edition:
        raise ValueError("Wrong feedback snapshot schema/edition")
    if not isinstance(data.get("rules", []), list) or not isinstance(data.get("excluded_urls", []), list):
        raise ValueError("Invalid snapshot lists")
    generated = _time(data["generated_at"])
    if generated > now + timedelta(minutes=5):
        raise ValueError("Snapshot is in the future")
    rules, seen = [], set()
    for rule in data.get("rules", []):
        if not isinstance(rule, dict) or rule.get("key") not in POLICY_KEYS:
            continue
        if rule.get("review_status") != "approved" or rule.get("version") != 1:
            continue
        if not isinstance(rule.get("enabled"), bool) or rule["key"] in seen:
            raise ValueError("Invalid or conflicting editorial switch")
        seen.add(rule["key"])
        rules.append({key: rule.get(key) for key in ("key", "enabled", "review_status", "updated_at", "version")})
    urls = []
    for entry in data.get("excluded_urls", []):
        value = safe_url(entry.get("url")) if isinstance(entry, dict) else ""
        if value and value not in urls:
            urls.append(value)
    stale = now - generated > timedelta(days=max_age_days)
    return {"rules": [] if stale else rules, "excluded_urls": urls,
            "status": "stale" if stale else "fresh", "generated_at": data["generated_at"]}


def load_feedback_snapshot(context, *, max_age_days=8, now=None):
    now = now or datetime.now(timezone.utc)
    empty = {"rules": [], "excluded_urls": [], "status": "missing", "generated_at": ""}
    path = snapshot_path(context)
    if not path.exists():
        return empty
    try:
        return _validated(json.loads(path.read_text(encoding="utf-8-sig")), context.id, now, max_age_days)
    except (ValueError, TypeError, KeyError, OSError):
        return {**empty, "status": "invalid"}


def snapshot_from_export(context, payload):
    if payload.get("edition") != context.id:
        raise ValueError("Export edition mismatch")
    articles = published_news(context.content_dir / "news_data.js")
    hidden = {str(row["item_id"]): row for row in payload.get("hidden", []) if row.get("item_kind", "news") == "news"}
    by_id = {}
    for article in articles:
        by_id.setdefault(article["id"], article)
    exclusions = {}
    for identity, row in hidden.items():
        candidates = [row.get("source_url")]
        article = by_id.get(identity)
        if article:
            candidates.extend([article["url"], *article.get("relatedUrls", [])])
        for candidate in candidates:
            url = safe_url(candidate)
            if url:
                exclusions[url] = {"url": url, "item_id": identity, "reason_code": row.get("reason_code", "other")}
    # Retained duplicate IDs must not reopen a hidden representative.
    for article in articles:
        target, visited = article, set()
        while target and target.get("id") not in visited:
            identity = target["id"]
            visited.add(identity)
            if identity in hidden:
                for candidate in [article["url"], *article.get("relatedUrls", [])]:
                    url = safe_url(candidate)
                    if url:
                        exclusions[url] = {"url": url, "item_id": identity, "reason_code": hidden[identity].get("reason_code", "other")}
                break
            target = by_id.get(target.get("duplicateOf"))
    return {"schema_version": 1, "edition": context.id,
            "generated_at": payload["generated_at"], "rules": payload.get("rules", []),
            "excluded_urls": list(exclusions.values())}


def remote_export_command(context):
    folder = "DailyNews" if context.id == "interior" else "DailyNewsExterior"
    snapshot_path(context)  # Validate before constructing a remote path.
    js = r'''
const {DatabaseSync}=require('node:sqlite');
const db=new DatabaseSync(DB_PATH,{readOnly:true});
db.exec('PRAGMA query_only=ON; BEGIN');
const tables=new Set(db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map(r=>r.name));
const columns=new Set(db.prepare('PRAGMA table_info(hidden_items)').all().map(r=>r.name));
const optional=(name,fallback)=>columns.has(name)?name:`${fallback} AS ${name}`;
const hidden=db.prepare('SELECT item_id,'+optional('reason_code',"'other'")+','+optional('item_kind',"'news'")+','+optional('source_url',"''")+' FROM hidden_items').all();
const rules=tables.has('selection_policy_approvals')?db.prepare('SELECT policy_key AS key,enabled,review_status,updated_at,version FROM selection_policy_approvals').all().map(r=>({...r,enabled:Boolean(r.enabled)})):[];
db.exec('ROLLBACK');db.close();
process.stdout.write(JSON.stringify({edition:EDITION_ID,generated_at:new Date().toISOString(),rules,hidden}));
'''.replace("DB_PATH", json.dumps(f"C:/Users/Administrator/Desktop/{folder}/data/dailynews.sqlite")).replace("EDITION_ID", json.dumps(context.id))
    b64 = base64.b64encode(js.encode("utf-8")).decode("ascii")
    ps = ("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"
          "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
          f"$editorialScript=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64}'));"
          "$editorialScript | & 'C:/Program Files/nodejs/node.exe' --no-warnings -;"
          "if($LASTEXITCODE -ne 0){throw 'Editorial settings export failed'}")
    encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    return ["ssh", "-i", str(Path.home() / ".ssh/dailynews_ieweb01"), "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15",
            "Administrator@IEWEB01", "powershell.exe -NoProfile -NonInteractive -EncodedCommand " + encoded]


def sync_feedback_snapshot(context, *, run=subprocess.run, timeout=45):
    """Keep the last successful snapshot if the read-only server query fails."""
    kwargs = {"capture_output": True, "text": True, "encoding": "utf-8", "timeout": timeout}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = run(remote_export_command(context), **kwargs)
    if result.returncode:
        raise RuntimeError("Editorial settings export failed")
    payload = json.loads(result.stdout.lstrip("\ufeff"))
    snapshot = snapshot_from_export(context, payload)
    validated = _validated(snapshot, context.id, datetime.now(timezone.utc), 8)
    snapshot["rules"] = validated["rules"]
    path = snapshot_path(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return {"status": "synced", "edition": context.id, "rule_count": len(snapshot["rules"]),
            "excluded_url_count": len(snapshot["excluded_urls"]), "generated_at": snapshot["generated_at"]}
