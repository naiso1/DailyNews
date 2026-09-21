"""Reference-image safety and cache tests. No network or provider calls."""
import dataclasses
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request
from unittest.mock import Mock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dailynews import exabase, exabase_reference as refs
from dailynews.editions import get_edition


def picture(color):
    image = Image.new("RGB", (384, 256), color)
    stream = io.BytesIO()
    image.save(stream, "JPEG")
    return stream.getvalue()


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.edition = get_edition("exterior", self.root)
        self.edition.config_dir.mkdir(parents=True)
        self.edition.collection_settings_path.write_text(json.dumps({"exterior": {"image_generation": {
            "enabled": True, "provider": "exabase", "reference_mode": "source-image"}}}), encoding="utf-8")
        self.edition.ensure_directories()
        self.text = 'window.DAILY_INSIGHTS=[{date:"2026-09-20",ideas:{jp:[{id:35,img:"images/existing.jpg",title:"前部加飾",desc:"配置を検討 [jp1]",sourceNewsIds:["jp1"]}]}}];'
        self.insights = self.edition.content_dir / "insights_data.js"
        self.insights.write_text(self.text, encoding="utf-8")
        self.sources = {"jp1": {"title": "新しい意匠", "desc": "前部の形状", "url": "https://example.com/article",
                                "img": "https://example.com/photo.jpg"}}
        (self.edition.content_dir / "news_data.js").write_text('window.NEWS_DATA=[{id:"jp1",title:"新しい意匠",desc:"前部の形状",url:"https://example.com/article",img:"https://example.com/photo.jpg"}];', encoding="utf-8")
        self.idea = exabase.select_ideas(self.text)[0]
        self.data = picture("blue")
        self.file = self.root / "reference.jpg"
        self.file.write_bytes(self.data)
        self.reference = refs.ReferenceImage("jp1", self.sources["jp1"]["url"], self.sources["jp1"]["img"], self.file,
            hashlib.sha256(self.data).hexdigest(), "image/jpeg", 384, 256)

    def worker(self, root, request, timeout):
        directory = Path(request["outputDir"])
        image = directory / "generated.jpg"
        image.write_bytes(picture("red"))
        exabase.atomic_json(directory / "phase.json", {"event": "done", "key": request["key"]})
        exabase.atomic_json(directory / "result.json", {"status": "DONE", "key": request["key"], "file": str(image)})

    def test_reference_cache_changes_with_bytes_mode_and_source_but_legacy_key_unchanged(self):
        prompt = exabase.image_prompt(self.idea, self.sources)
        legacy = {"edition": "exterior", "idea_id": self.idea.id, "date": self.idea.date, "sources": self.idea.sources,
                  "prompt": prompt, "engine": exabase.ENGINE_SHA, "prompt_version": 1}
        old = hashlib.sha256(json.dumps(legacy, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.assertEqual(exabase.job_key("exterior", self.idea, prompt), old)
        key = exabase.job_key("exterior", self.idea, prompt, self.reference)
        self.assertNotEqual(key, old)
        for changed in (dataclasses.replace(self.reference, sha256="f" * 64),
                        dataclasses.replace(self.reference, image_url="https://example.com/other.jpg")):
            self.assertNotEqual(exabase.job_key("exterior", self.idea, prompt, changed), key)

    def test_explicit_comparison_keeps_published_image_and_saves_attachment_and_cache(self):
        worker = Mock(side_effect=self.worker)
        loader = Mock(return_value=self.reference)
        report = exabase.generate_for_edition(self.edition, pilot_idea_id=35, date="2026-09-20", publish=False,
            reference_source_id="jp1", reference_loader=loader, worker=worker)
        self.assertEqual(report["generated"], 1)
        request = worker.call_args.args[1]
        self.assertEqual(Path(request["referenceImage"]["file"]).read_bytes(), self.data)
        self.assertIn("車種、ブランド、ロゴ、背景", request["prompt"])
        manifest = exabase.read_json(Path(request["outputDir"]) / "manifest.json")
        self.assertEqual(manifest["referenceImage"], self.reference.metadata())
        repeated = exabase.generate_for_edition(self.edition, pilot_idea_id=35, date="2026-09-20", publish=False,
            reference_source_id="jp1", reference_loader=loader, worker=worker)
        self.assertEqual(repeated["cached"], 1)
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(self.insights.read_text(encoding="utf-8"), self.text)
        self.assertFalse((self.edition.runtime_dir / "exabase-last-result.json").exists())

    def test_comparison_cannot_publish_or_select_uncited_image(self):
        with self.assertRaises(ValueError):
            exabase.generate_for_edition(self.edition, pilot_idea_id=35, date="2026-09-20", reference_source_id="jp1")
        worker = Mock()
        report = exabase.generate_for_edition(self.edition, pilot_idea_id=35, date="2026-09-20", publish=False,
                                             reference_source_id="cn1", worker=worker)
        self.assertEqual(report["errors"][0]["code"], "INVALID_SOURCE_IDS")
        with patch.object(exabase, "source_articles", return_value={}):
            missing = exabase.generate_for_edition(self.edition, pilot_idea_id=35, date="2026-09-20", publish=False,
                                                  reference_source_id="jp1", worker=worker)
            self.assertEqual(missing["errors"][0]["code"], "INVALID_SOURCE_IDS")
        worker.assert_not_called()

    def test_missing_reference_download_falls_back_to_text_without_api(self):
        self.insights.write_text(self.text.replace('images/existing.jpg', ''), encoding="utf-8")
        worker = Mock(side_effect=self.worker)
        loader = Mock(side_effect=refs.ReferenceImageError("REFERENCE_DOWNLOAD_FAILED"))
        report = exabase.generate_for_edition(self.edition, worker=worker, reference_loader=loader)
        self.assertEqual(report["generated"], 1)
        self.assertEqual(report["warnings"][0]["fallback"], "text-only")
        self.assertNotIn("referenceImage", worker.call_args.args[1])
        self.assertEqual(report["images"][0]["reference_mode"], "text-only")

    def test_changed_attachment_and_source_mismatch_fail_before_worker(self):
        worker = Mock()
        self.file.write_bytes(picture("green"))
        with self.assertRaisesRegex(exabase.ImageJobError, "REFERENCE_CHANGED"):
            exabase.generate_one(self.edition, self.idea, self.sources, worker=worker, reference=self.reference)
        with self.assertRaisesRegex(exabase.ImageJobError, "INVALID_SOURCE_IDS"):
            exabase.generate_one(self.edition, self.idea, self.sources, worker=worker,
                                 reference=dataclasses.replace(self.reference, source_id="cn1"))
        worker.assert_not_called()

    def test_submitted_reference_timeout_never_automatically_resubmits(self):
        def uncertain(root, request, timeout):
            exabase.atomic_json(Path(request["outputDir"]) / "phase.json", {"event": "sending", "key": request["key"]})
            raise exabase.ImageJobError("WORKER_TIMEOUT")
        worker = Mock(side_effect=uncertain)
        with self.assertRaisesRegex(exabase.ImageJobError, "WORKER_TIMEOUT"):
            exabase.generate_one(self.edition, self.idea, self.sources, worker=worker, reference=self.reference)
        with self.assertRaisesRegex(exabase.ImageJobError, "NEEDS_REVIEW"):
            exabase.generate_one(self.edition, self.idea, self.sources, worker=worker, reference=self.reference)
        self.assertEqual(worker.call_count, 1)
        self.file.write_bytes(picture("green"))
        changed = dataclasses.replace(self.reference, sha256=hashlib.sha256(self.file.read_bytes()).hexdigest())
        with self.assertRaisesRegex(exabase.ImageJobError, "NEEDS_REVIEW"):
            exabase.generate_one(self.edition, self.idea, self.sources, worker=worker, reference=changed)
        with self.assertRaisesRegex(exabase.ImageJobError, "NEEDS_REVIEW"):
            exabase.generate_one(self.edition, self.idea, self.sources, worker=worker)
        self.assertEqual(worker.call_count, 1)

    def test_same_url_changed_image_bytes_produce_a_new_job_after_completed_result(self):
        worker = Mock(side_effect=self.worker)
        _, old_key, _ = exabase.generate_one(self.edition, self.idea, self.sources, worker=worker, reference=self.reference)
        self.file.write_bytes(picture("green"))
        changed = dataclasses.replace(self.reference, sha256=hashlib.sha256(self.file.read_bytes()).hexdigest())
        _, new_key, _ = exabase.generate_one(self.edition, self.idea, self.sources, worker=worker, reference=changed)
        self.assertNotEqual(old_key, new_key)
        self.assertEqual(worker.call_count, 2)

    def test_private_urls_credentials_and_non_http_are_rejected(self):
        for url in ('file:///image.jpg', 'https://user:pass@example.com/a.jpg', 'http://127.0.0.1/a',
                    'http://169.254.169.254/a', 'http://[::1]/a', 'http://intranet/a', 'http://example.com:123/a'):
            with self.subTest(url=url), self.assertRaises(refs.ReferenceImageError):
                refs.public_url(url, resolve=False)
        with patch.object(refs.socket, 'getaddrinfo', return_value=[(2,1,6,'',('10.1.2.3',443))]):
            with self.assertRaises(refs.ReferenceImageError):
                refs.public_url('https://example.com/a')

    def test_non_image_small_animated_and_oversize_bytes_rejected(self):
        for data in (b'<html>' * 1000, b'abc', b'x' * (refs.MAX_BYTES + 1)):
            with self.assertRaises(refs.ReferenceImageError):
                refs.image_info(data)
        self.assertEqual(refs.image_info(self.data)[0], 'image/jpeg')
        stream = io.BytesIO()
        Image.new('RGB',(128,128)).save(stream,'PNG')
        with self.assertRaises(refs.ReferenceImageError):
            refs.image_info(stream.getvalue())

    def test_download_records_actual_image_hash_and_rejects_html_or_private_redirect(self):
        headers = Message()
        headers['Content-Type'] = 'image/jpeg'
        class Response(io.BytesIO):
            def geturl(self):
                return 'https://example.com/photo.jpg'
        response = Response(self.data)
        response.headers = headers
        opener = Mock()
        opener.open.return_value = response
        with patch.object(refs.socket, 'getaddrinfo', return_value=[(2,1,6,'',('93.184.216.34',443))]):
            result = refs.download_reference('jp1', self.sources['jp1'], self.root/'download', opener=opener)
        self.assertEqual(result.sha256, hashlib.sha256(self.data).hexdigest())
        self.assertEqual(result.file.read_bytes(), self.data)
        self.assertEqual(result.metadata()['articleUrl'], self.sources['jp1']['url'])
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 20)
        response = Response(b'<html>not an image</html>' * 100)
        headers.replace_header('Content-Type', 'text/html')
        response.headers = headers
        opener.open.return_value = response
        with patch.object(refs.socket, 'getaddrinfo', return_value=[(2,1,6,'',('93.184.216.34',443))]):
            with self.assertRaisesRegex(refs.ReferenceImageError, 'REFERENCE_INVALID_IMAGE'):
                refs.download_reference('jp1', self.sources['jp1'], self.root/'download', opener=opener)
        with self.assertRaisesRegex(refs.ReferenceImageError, 'REFERENCE_URL_REJECTED'):
            refs.PublicRedirects().redirect_request(urllib.request.Request('https://example.com/photo.jpg'),
                None, 302, '', {}, 'http://127.0.0.1/private')


if __name__ == '__main__':
    unittest.main()
