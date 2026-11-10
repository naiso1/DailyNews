"""Resume missing current-issue images under run.py's workstation lock.

No collection, mail, interactive sign-in, API fallback, or uncertain resubmission.
The private journal owns only verified additions to image fields; a failed
publication is resumed before attempting any more generation.
"""
import datetime as dt
import hashlib
import importlib.util
import os
import re
import subprocess

from dailynews import exabase, copilot, idea_images
from dailynews.editions import get_edition

JST = dt.timezone(dt.timedelta(hours=9))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_session(root):
    # Reuse bounded child cleanup and safe status parsing, without taking the
    # workstation lock twice or invoking the maintenance task's main().
    spec = importlib.util.spec_from_file_location(
        'image_recovery_session', root / 'deployment/workstation/exabase/maintain-session.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Recovery must not be blocked by exaBase expiry when Copilot is usable.
    if any(get_edition(name, root).image_generation.get('provider') == 'copilot'
           for name in ('interior', 'exterior')):
        result = copilot.check_session(root)
        if result[0] == 'authenticated':
            return result
    return module.refresh(root)


def latest_issue(edition, today):
    config = edition.image_generation
    if (not config.get('enabled') or config.get('provider') not in {'exabase', 'copilot'}
            or config.get('fallback_provider', 'none') not in {'none', 'exabase'}):
        return None
    status = exabase.read_json(edition.runtime_dir / 'logs/latest_run_status.json', {})
    expected = (today - dt.timedelta(days=1)).isoformat()
    if (status.get('edition_id') != edition.id or status.get('status') != 'success'
            or status.get('run_date') != today.isoformat()
            or status.get('published_news_date') != expected):
        return None
    text = (edition.content_dir / 'insights_data.js').read_text(encoding='utf-8')
    ideas = exabase.select_ideas(text)
    if not ideas or max(re.findall(r'\d{4}-\d{2}-\d{2}', ideas[0].date), default='') != expected:
        return None
    return ideas[0].date, text, ideas


def image_additions(edition, before, after, issue):
    """Exact reconstruction rejects changes to prose, archives or existing images."""
    original = exabase.select_ideas(before, date=issue)
    current = exabase.select_ideas(after, date=issue)
    if not original or [i.id for i in original] != [i.id for i in current]:
        raise ValueError('CONTENT_CHANGED')
    expected = before
    paths = []
    for first, last in zip(original, current):
        if not exabase.same_brief(first, last):
            raise ValueError('CONTENT_CHANGED')
        if (first.image, first.image_provider, first.image_model) == (last.image, last.image_provider, last.image_model):
            continue
        pattern = rf'images/{re.escape(last.image_provider)}_{edition.id}_{first.id}_[a-f0-9]{{16}}\.(png|jpg|webp)'
        valid_model = ((last.image_provider == 'exabase' and last.image_model in {'GPT-image', 'Nano Banana'})
                       or (last.image_provider == 'copilot' and last.image_model == ''))
        if (exabase.has_image(first) or not exabase.has_image(last)
                or not valid_model
                or not re.fullmatch(pattern, last.image)):
            raise ValueError('CONTENT_CHANGED')
        file = edition.content_dir / last.image
        if not file.resolve().is_relative_to((edition.content_dir / 'images').resolve()):
            raise ValueError('CONTENT_CHANGED')
        exabase.valid_image(file)
        idea = exabase.select_ideas(expected, date=issue, idea_id=first.id)[0]
        expected = exabase.image_fields(expected, idea, img=last.image,
                                       imageProvider=last.image_provider, imageModel=last.image_model)
        paths.append(file)
    if expected != after:
        raise ValueError('CONTENT_CHANGED')
    return paths


def command(root, args, timeout=120):
    process = subprocess.Popen(args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill only this command's tree, so a timed-out deploy cannot overlap the
        # next retry after run.lock is released. Never terminate other sessions.
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                               capture_output=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
        raise RuntimeError('IMAGE_PUBLICATION_FAILED') from None
    if process.returncode:
        # Do not put raw provider, Git credential or server output into the log.
        raise RuntimeError('IMAGE_PUBLICATION_FAILED')
    return output.strip()


def publish(edition, images):
    """Commit only this repair, push, then use the normal release deployment."""
    root = edition.root
    paths = [(edition.content_dir / 'insights_data.js').relative_to(root).as_posix()]
    paths += [p.relative_to(root).as_posix() for p in images]
    staged = command(root, ['git', '-c', 'core.quotepath=false', 'diff', '--cached', '--name-only']).splitlines()
    if set(staged) - set(paths):
        raise RuntimeError('OTHER_STAGED_CHANGES')
    command(root, ['git', 'add', '--', *paths])
    if command(root, ['git', 'diff', '--cached', '--name-only']):
        command(root, ['git', 'commit', '-m', f'Recover {edition.id} current issue idea images'])
    public = ['内装製品デイリーニュース.html', 'header-layout-test.html', 'activity-preview.html',
              'source-list-preview.html', 'currency-conversion-preview.html', 'exchange_rates.js',
              'dailynews_annotations.js', 'dailynews_exterior_tags.js', 'dailynews_event_tags.js',
              'dailynews_config.js', 'dailynews_client.js', 'dailynews_account.js', 'dailynews_reports.js',
              'dailynews_activity.js', 'dailynews_sources.js', 'release_history.js', 'dailynews_header.js',
              'dailynews_header.css', 'news_data.js', 'insights_data.js', 'source_list_data.js',
              'setup', 'images', 'page_images', 'content/exterior']
    # The exterior packager uses working-tree files. Do not include unrelated
    # uncommitted UI/data changes in an automatic image-only release.
    if command(root, ['git', 'status', '--porcelain', '--untracked-files=normal', '--', *public]):
        raise RuntimeError('OTHER_PUBLIC_CHANGES')
    try:
        command(root, ['git', '-c', 'credential.interactive=false', 'push', 'origin', 'HEAD:main'], 180)
    except RuntimeError:
        command(root, ['git', '-c', 'credential.interactive=false', '-c',
                       'http.proxy=' + os.environ.get('HTTPS_PROXY', ''), 'push',
                       'https://github.com/naiso1/DailyNews.git', 'HEAD:refs/heads/main'], 180)
    command(root, ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                   '-File', str(root / 'deployment/windows-server/deploy.ps1'), '-Edition', edition.id], 1800)


def recover_latest_images(root, runtime, editions, *, today=None, auth=None,
                          generate=None, publisher=None, publication_reader=None):
    """Return editions whose image-only repair is owned; don't collect them again.

    Caller must hold run.lock and validate the configured host. A private baseline
    is durable before generation, so power loss cannot turn a partial image repair
    into an unrecognized data change and a full collection rerun.
    """
    today = today or dt.datetime.now(JST).date()
    if today.weekday() >= 5:
        return set()
    if publication_reader is None:
        from recovery import published_hashes
        publication_reader = published_hashes
    auth = auth or check_session
    generate = generate or idea_images.optional_images
    publisher = publisher or publish
    owned = set()
    auth_result = None
    for name in editions:
        edition = get_edition(name, root)
        journal_path = runtime / 'image-recovery' / name / 'state.json'
        state = None
        try:
            candidate = latest_issue(edition, today)
            if not candidate:
                continue
            issue, text, ideas = candidate
            state = exabase.read_json(journal_path, {})
            key = {'day': today.isoformat(), 'issue': issue, 'edition': name}
            matches = all(state.get(k) == v for k, v in key.items())
            missing = any(not exabase.has_image(i) for i in ideas)
            if not missing and not matches:
                continue
            news_hash = digest(edition.content_dir / 'news_data.js')
            if not matches:
                remote = publication_reader(name)
                if remote != {'news_data.js': news_hash,
                              'insights_data.js': digest(edition.content_dir / 'insights_data.js')}:
                    # Another unpublished edit belongs to the normal pipeline.
                    continue
                state = {**key, 'baseline': text, 'news_hash': news_hash, 'attempts': 0,
                         'status': 'waiting'}
                exabase.atomic_json(journal_path, state)
            # A repair journal for this completed issue also owns conflicts:
            # pause for review rather than falling through to a full collection
            # that could overwrite a person's intervening content edits.
            owned.add(name)
            if state['news_hash'] != news_hash:
                raise ValueError('CONTENT_CHANGED')
            additions = image_additions(edition, state['baseline'], text, issue)
            if not missing and not additions:
                # Normal completion/health checks still apply after the repair.
                owned.discard(name)
                continue
            # Always finish a partial/crashed publication before generating more.
            if not additions and missing and state['attempts'] < 2:
                if auth_result is None:
                    auth_result = auth(root)
                status, code = auth_result
                if status != 'authenticated':
                    state.update(status=status, code=code)
                    exabase.atomic_json(journal_path, state)
                    continue
                state.update(status='generating', code='', attempts=state['attempts'] + 1)
                exabase.atomic_json(journal_path, state)
                report = generate(edition, issue_date=issue)
                text = (edition.content_dir / 'insights_data.js').read_text(encoding='utf-8')
                additions = image_additions(edition, state['baseline'], text, issue)
                codes = {e['code'] for e in report.get('errors', []) if isinstance(e.get('code'), str)}
                if codes & {'AUTH_REQUIRED', 'SETUP_REQUIRED', 'BUSY'}:
                    # Expiry/busy is not a spent generation retry. Re-check next
                    # time; the original job receipts still prevent double sends.
                    state['attempts'] -= 1
                    auth_result = ('action_required', next(c for c in ('AUTH_REQUIRED', 'SETUP_REQUIRED', 'BUSY') if c in codes))
                state['code'] = next((c for c in sorted(codes) if c in exabase.SAFE_CODES), '')
            if digest(edition.content_dir / 'news_data.js') != news_hash:
                raise ValueError('CONTENT_CHANGED')
            if additions:
                state['status'] = 'publication_pending'
                exabase.atomic_json(journal_path, state)
                publisher(edition, additions)
                remote = publication_reader(name)
                if remote != {'news_data.js': news_hash,
                              'insights_data.js': digest(edition.content_dir / 'insights_data.js')}:
                    raise RuntimeError('IMAGE_PUBLICATION_FAILED')
                state['baseline'] = text
            current = exabase.select_ideas(text, date=issue)
            state['missing'] = [i.id for i in current if not exabase.has_image(i)]
            state['status'] = 'complete' if not state['missing'] else 'waiting'
            exabase.atomic_json(journal_path, state)
            print(f'IMAGE RECOVERY {name}: {state["status"]}, missing={len(state["missing"])}', flush=True)
        except Exception as error:
            # A validated journal remains owned even if generation/deploy fails.
            # Never leak provider responses or silently lose the repair state.
            code = str(error) if str(error) in {'CONTENT_CHANGED', 'IMAGE_PUBLICATION_FAILED', 'OTHER_STAGED_CHANGES', 'OTHER_PUBLIC_CHANGES'} else 'IMAGE_RECOVERY_UNAVAILABLE'
            if state and journal_path.exists():
                state.update(status='error', code=code)
                exabase.atomic_json(journal_path, state)
            print(f'IMAGE RECOVERY {name}: {code}', flush=True)
    return owned
