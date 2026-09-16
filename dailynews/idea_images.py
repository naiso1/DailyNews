"""Latest-issue image generation: exaBase first, optional interior-only API fallback."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

from . import exabase

API_CODES = {"API_KEY_MISSING", "API_HTTP_ERROR", "API_HTTP_REJECTED", "API_NO_IMAGE", "API_UNAVAILABLE", "API_NEEDS_REVIEW"}


def generate_api_bytes(edition, idea, model):
    """Reuse the existing Gemini brief, reference images, proxy and request settings."""
    import generate_idea_images_gemini as gemini

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise exabase.ImageJobError("API_KEY_MISSING")
    gemini.configure_external_proxy()
    news = gemini.extract_news_reference_map((edition.content_dir / "news_data.js").read_text(encoding="utf-8"))
    reference_parts = gemini.build_reference_parts({"id": idea.id, "sourceNewsIds": idea.sources}, news, max_images=2)
    prompt = gemini.build_prompt(idea.title, idea.desc, idea.image_prompt, has_references=bool(reference_parts))
    api_version = os.environ.get("GEMINI_API_VERSION", gemini.DEFAULT_API_VERSION).strip() or gemini.DEFAULT_API_VERSION
    payload = {
        "contents": [{"parts": [{"text": prompt}, *reference_parts]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {
            "aspectRatio": os.environ.get("GEMINI_IMAGE_ASPECT_RATIO", "1:1").strip() or "1:1",
            "imageSize": os.environ.get("GEMINI_IMAGE_SIZE", "512px").strip() or "512px",
        }},
    }
    response = gemini.requests.post(
        f"https://generativelanguage.googleapis.com/{api_version}/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}, json=payload, timeout=300,
    )
    if response.status_code >= 400:
        # Timeouts and server/proxy failures do not prove the generation was rejected.
        code = "API_HTTP_REJECTED" if response.status_code in {400, 401, 403, 404, 413, 415, 422, 429} else "API_HTTP_ERROR"
        raise exabase.ImageJobError(code)
    raw = gemini.parse_first_image_bytes(response.json())
    if not raw:
        raise exabase.ImageJobError("API_NO_IMAGE")
    return raw


def api_image(edition, idea, model, generator):
    brief = {"edition": edition.id, "id": idea.id, "date": idea.date, "title": idea.title,
             "desc": idea.desc, "prompt": idea.image_prompt, "sources": idea.sources, "model": model,
             "image_size": os.environ.get("GEMINI_IMAGE_SIZE", "512px"),
             "aspect_ratio": os.environ.get("GEMINI_IMAGE_ASPECT_RATIO", "1:1")}
    key = hashlib.sha256(json.dumps(brief, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    directory = edition.runtime_dir / "api-image-jobs" / key
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path, image_path = directory / "result.json", directory / "image.bin"
    receipt = exabase.read_json(receipt_path, {})
    if image_path.exists():
        _, digest = exabase.valid_image(image_path)
        if receipt.get("image_sha256") and receipt["image_sha256"] != digest:
            raise exabase.ImageJobError("INVALID_IMAGE")
        return image_path, key, True
    if receipt.get("status") in {"submitted", "needs_review"}:
        raise exabase.ImageJobError("API_NEEDS_REVIEW")
    receipt = {"provider": "api", "model": model, "idea_id": idea.id, "date": idea.date,
               "key": key, "status": "submitted"}
    exabase.atomic_json(receipt_path, receipt)
    try:
        raw = generator(edition, idea, model)
        temp = directory / "image.tmp"
        temp.write_bytes(raw)
        _, digest = exabase.valid_image(temp)
        os.replace(temp, image_path)
        receipt.update(status="done", image_sha256=digest)
        exabase.atomic_json(receipt_path, receipt)
        return image_path, key, False
    except Exception as error:
        code = str(error) if isinstance(error, exabase.ImageJobError) and str(error) in API_CODES | exabase.SAFE_CODES else "API_UNAVAILABLE"
        # Only a missing key or an explicit rejection permits automatic resubmission.
        receipt.update(status="retryable" if code in {"API_KEY_MISSING", "API_HTTP_REJECTED"} else "needs_review", code=code)
        exabase.atomic_json(receipt_path, receipt)
        raise exabase.ImageJobError(code) from error


def optional_images(edition, *, issue_date=None, exabase_runner=None, api_generator=None):
    """Image failures never fail text publication; never backfill a previous issue."""
    report = {"status": "disabled", "generated": 0, "cached": 0, "images": [], "errors": [], "providers": {}}
    config = edition.image_generation
    if not config.get("enabled") or config.get("provider") not in {"exabase", "gemini"}:
        return report
    path = edition.content_dir / "insights_data.js"
    if not path.exists():
        report["status"] = "no_ideas"
        return report
    try:
        with exabase.edition_lock(edition.runtime_dir / "idea-images.lock"):
            ideas = exabase.select_ideas(path.read_text(encoding="utf-8"))
            if not ideas or (issue_date and ideas[0].date != issue_date):
                report["status"] = "no_current_ideas"
                return report
            date = ideas[0].date
            dates = re.findall(r"\d{4}-\d{2}-\d{2}", date)
            if config.get("start_after_date") and (not dates or max(dates) <= config["start_after_date"]):
                report["status"] = "before_start_date"
                return report
            report.update(status="complete", date=date)
            if config.get("provider") == "exabase":
                try:
                    primary = (exabase_runner or exabase.generate_for_edition)(edition, date=date)
                except Exception as error:
                    code = str(error) if isinstance(error, exabase.ImageJobError) and str(error) in exabase.SAFE_CODES else "EXABASE_UNAVAILABLE"
                    primary = {"errors": [{"code": code}]}
                report["exabase_status"] = primary.get("status", "unavailable")
                for field in ("generated", "cached"):
                    report[field] += primary.get(field, 0)
                report["images"].extend(primary.get("images", []))
                report["errors"].extend(primary.get("errors", []))

            # Paid API is authorized for interior only, even if an exterior setting is mistyped.
            use_api = edition.id == "interior" and (
                config.get("provider") == "gemini" or config.get("fallback_provider") == "gemini")
            # Another browser job may still be generating these images. Do not
            # race it with a paid API request; preserve text and retry after the lock clears.
            if any(error.get("code") == "BUSY" for error in report["errors"]):
                use_api = False
                report["fallback_deferred"] = "BUSY"
            if use_api:
                # The direct exaBase CLI shares this lock. Re-read under it so a
                # manual generation cannot race fallback between provider calls.
                with exabase.edition_lock(edition.runtime_dir / "exabase.lock"):
                    latest = exabase.select_ideas(path.read_text(encoding="utf-8"), date=date)
                    limit = max(1, min(int(config.get("max_images", 10)), 20))
                    available = max(0, limit - sum(exabase.has_image(idea) for idea in latest))
                    pending = [idea for idea in latest if not exabase.has_image(idea)][:available]
                    model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview").strip() or "gemini-3.1-flash-image-preview"
                    sources = exabase.source_articles((edition.content_dir / "news_data.js").read_text(encoding="utf-8"))
                    for idea in pending:
                        try:
                            # Apply the same source checks to either provider.
                            exabase.image_prompt(idea, sources, edition.id)
                            image, key, cached = api_image(edition, idea, model, api_generator or generate_api_bytes)
                            current_text = path.read_text(encoding="utf-8")
                            current = exabase.select_ideas(current_text, date=date, idea_id=idea.id)
                            if len(current) != 1 or exabase.has_image(current[0]) or not exabase.same_brief(current[0], idea):
                                raise exabase.ImageJobError("CONTENT_CHANGED")
                            location = exabase.publish_image(edition, current_text, current[0], image, key, provider="api", model=model)
                            report["cached" if cached else "generated"] += 1
                            report["images"].append({"idea_id": idea.id, "provider": "api", "model": model, "image": location})
                        except Exception as error:
                            code = str(error) if isinstance(error, exabase.ImageJobError) and str(error) in API_CODES | exabase.SAFE_CODES else "API_UNAVAILABLE"
                            report["errors"].append({"idea_id": idea.id, "provider": "api", "code": code})
                            if code == "API_KEY_MISSING":
                                break
            final = exabase.select_ideas(path.read_text(encoding="utf-8"), date=date)
            for idea in final:
                if exabase.has_image(idea) and idea.image_provider in {"exabase", "api"}:
                    report["providers"][idea.image_provider] = report["providers"].get(idea.image_provider, 0) + 1
            report["missing"] = [idea.id for idea in final if not exabase.has_image(idea)]
            if report["missing"]:
                report["status"] = "partial" if any(exabase.has_image(idea) for idea in final) else "unavailable"
            exabase.atomic_json(edition.runtime_dir / "image-generation-last-result.json", report)
    except Exception as error:
        code = str(error) if isinstance(error, exabase.ImageJobError) and str(error) in exabase.SAFE_CODES else "IMAGE_GENERATION_UNAVAILABLE"
        report.update(status="unavailable")
        report["errors"].append({"code": code})
        if code == "BUSY":
            report["fallback_deferred"] = "BUSY"
    return report
