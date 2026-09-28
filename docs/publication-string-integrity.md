# Preserve article text when inserting JavaScript data

On 2026-09-28 the interior collection completed, but publication stopped in
`merge_related_sources` with `JSONDecodeError: Invalid \\escape`. The previous
published issue therefore remained visible and the success-mail gate stayed closed.

## Cause

`js_escape` escaped source text for a JavaScript string. `append_news_items` then
passed the generated block as the replacement string of `re.sub`. Python interpreted
its backslashes again. A source fragment ending in `\\。` became an invalid JSON
string when the generated article history was read back. Literal `\\n` and regular
expression replacement references could also be corrupted. `insert_insight` used
the same unsafe insertion pattern.

## Fix

- Use callable replacements to insert both news and insight blocks verbatim.
- Serialize string contents through `json.dumps`, including control characters.
- Preserve existing newline and Unicode line-separator normalization.
- Keep the strict history validation; do not silently discard unparseable articles.

Regression tests cover the failure fragment, literal backslash sequences,
replacement references, quotes, apostrophes, newlines, tabs, control characters,
insight insertion and preservation of existing history. The language-validation
test now uses valid stored history so it reaches the incoming-language guard.

The original collected CSV was backed up privately. One unprocessed gallery
description was quarantined for this recovery, with its substantive related article
retained. The complete original 50-item batch also passed a dry run after the code
fix; removing the gallery is a content decision, not the crash workaround.

Run the focused checks from the repository root:

```powershell
$env:PYTHONPATH="$PWD\tests"
python -m unittest tests.test_publication_string_integrity tests.test_publication_deduplication tests.test_publication_language tests.test_resume_publication
```

31 tests passed. Recovery must still finish insight generation, publish the current
issue, verify the live release and dated success feed, and only then send through
the existing newsletter flow. Never infer successful delivery from a local build.
