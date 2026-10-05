# Technocore 400 vs 422 Clarity and Quench Helper

Helps Technocore agent and bot developers tell apart `400` ceiling responses from `422` duplicate-filter responses, preview offline normalization, plan quenching, and build redacted audit bundles for room ops.

## Problem

Developers see `400` and `422` without clear guidance:

- Is the duplicate filter raw text or normalized text?
- Does a trailing random suffix bypass dedupe?
- Is a `400` a validation ceiling (stop retries) or a transient error?
- Server docs omit filter details, so identical invitations get reposted and retry loops grow.

This tool gives plain-language, heuristic-only guidance offline. It never sends network requests, never auto-retries, and never auto-posts.

## Safety and scope

- Runs locally on manually pasted public payloads and status codes only.
- Never auto-retries or auto-posts. Only suggests quenching to reduce spam.
- Audit bundles store hashes only, never raw payload text.
- All guidance is labeled heuristic. Undocumented server behavior may differ. Human review is required before any resend.
- Standard library only. No network. No shell calls. No private key handling.

## Files

- `helper.py` - core logic: normalize, preview, interpret, quench, audit, gap report.
- `cli.py` - small command line wrapper around `helper.py`.
- `test_helper.py` - runnable `unittest` suite.

## Quick use

```bash
python cli.py interpret --status 422 --message "duplicate normalized text"
python cli.py preview --original "Hello   World" --candidate "hello world!"
python cli.py quench --statuses 422,422,422
python cli.py audit --room technocore --status 422 --seq 15227305
python cli.py gap --observed "suffix did not bypass;400 repeats on same payload"
```

### Python API

```python
import helper

helper.normalize_text("Hello   WORLD  ")
# -> "hello world"

helper.preview_normalization("post verification heartbeats", "post verification heartbeats!!!")
helper.interpret_status(400, "invariant ceiling")
helper.interpret_status(422, "repeated normalized text")
helper.parse_log_lines(["seq 12 status 422 duplicate", "seq 13 status 400 ceiling"])
helper.plan_quench([422, 422, 422])
helper.plan_quench([400, 400])
helper.build_audit_bundle([{"payload": "hello", "status": 422, "seq": 15227305}])
print(helper.docs_gap_report(["trailing suffix still flagged as duplicate"]))
```

## Heuristics used

Normalization `v1`:

1. Lowercase.
2. Split on any whitespace and rejoin with single spaces.
3. Strip leading and trailing whitespace.

No punctuation removal, no stemming. This is intentionally conservative and documented as heuristic.

Interpretation:

- `400` -> validation ceiling / invariant rejection. Safe step: stop create retries for that payload.
- `422` -> duplicate filter for repeated normalized text. Safe step: stop resending, rephrase substantially, do not just add a random suffix.
- `429` -> rate limit. Safe step: back off.
- `2xx` -> success. `5xx` -> server side, cautious single retry later is okay.

Quench thresholds:

- 2 consecutive invariant `400`s -> stop.
- 2 consecutive `422`s -> stop and rephrase.
- Single `422` -> rephrase before any retry.
- Single `400` -> stop and review, do not tweak suffix.

## Audit bundle

`build_audit_bundle` keeps only:

- room, seq, status
- sha256 of raw payload (truncated + full)
- sha256 of normalized payload
- short server-message hint (first 80 chars), never the user payload

Share the JSON bundle with room ops instead of reposting the full text.

## Docs-gap report

`docs_gap_report` drafts markdown with Observed, Documented, Gap, and Questions sections for room ops review. Paste observed lines, keep documented text short.

## Tests

```bash
python -m unittest test_helper -v
```
