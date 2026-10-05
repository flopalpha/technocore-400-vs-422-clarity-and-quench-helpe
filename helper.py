"""Technocore 400 vs 422 clarity and quench helper.

Offline, heuristic-only guidance. Never sends network requests.
Distinguishes 400 ceiling from 422 duplicate filter, previews
normalization, plans quenching, builds redacted audit bundles,
and drafts docs-gap reports.
"""
import hashlib
import json
import re

NORMALIZATION_VERSION = "v1"
STOP_AFTER_400 = 2
STOP_AFTER_422 = 2

DOCUMENTED_BEHAVIOR = (
    "Server docs describe generic 400 validation and 422 unprocessable "
    "responses but omit spam-filter and duplicate-filter details."
)

_STATUS_RE = re.compile(r"\b(200|201|204|400|422|429|500|503)\b")


def normalize_text(text):
    """Return canonical preview form: lower, collapse whitespace, strip."""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    lowered = text.lower()
    parts = lowered.split()
    return " ".join(parts)


def hash_text(text):
    """Return sha256 hex digest of text."""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def trailing_token_diff(a, b):
    """Compare normalized token lists and report trailing change."""
    if not isinstance(a, str) or not isinstance(b, str):
        raise TypeError("inputs must be str")
    at = normalize_text(a).split()
    bt = normalize_text(b).split()
    common = 0
    limit = len(at) if len(at) < len(bt) else len(bt)
    while common < limit and at[common] == bt[common]:
        common += 1
    if len(at) <= len(bt):
        added = bt[common:]
    else:
        added = []
    only_suffix = False
    if at and bt:
        if common == len(at) and len(bt) > len(at):
            only_suffix = True
        if common == len(bt) and len(at) > len(bt):
            only_suffix = True
    return {
        "a_tokens": at,
        "b_tokens": bt,
        "common_prefix_len": common,
        "added_tokens": added,
        "only_suffix_changed": only_suffix,
    }


def preview_normalization(original, candidate):
    """Preview canonical forms without sending anything."""
    if not isinstance(original, str) or not isinstance(candidate, str):
        raise TypeError("inputs must be str")
    norm_a = normalize_text(original)
    norm_b = normalize_text(candidate)
    match = norm_a == norm_b and norm_a != ""
    diff = trailing_token_diff(original, candidate)
    if match:
        guidance = "Would likely still match duplicate filter. Rephrase body, do not just add suffix."
    elif diff["only_suffix_changed"]:
        guidance = "Only trailing tokens changed. Heuristic: still risky, rephrase earlier words too."
    elif norm_a == "" or norm_b == "":
        guidance = "One side is empty after normalization. Add real distinct content."
    else:
        guidance = "Normalized forms differ. Still quench and review before any resend."
    return {
        "normalization_version": NORMALIZATION_VERSION,
        "original_normalized": norm_a,
        "candidate_normalized": norm_b,
        "original_hash": hash_text(norm_a),
        "candidate_hash": hash_text(norm_b),
        "match": match,
        "trailing_diff": diff,
        "guidance": guidance,
        "heuristic_only": True,
    }


def interpret_status(status, message=""):
    """Map pasted status code and message to plain cause and next steps."""
    if not isinstance(status, int):
        raise TypeError("status must be int")
    if message is None:
        message = ""
    if not isinstance(message, str):
        raise TypeError("message must be str")
    low = message.lower()
    if status == 400:
        return {
            "status": 400,
            "category": "ceiling_400",
            "plain_cause": "Validation ceiling or invariant rejection, not a duplicate filter.",
            "detail": "Past note mentioned invariant 400 ceiling. Repeating the same create will keep failing.",
            "should_retry_same_payload": False,
            "safe_next_steps": [
                "Stop create retries for this exact payload.",
                "Do not tweak only a suffix; review limits and required fields.",
                "Change approach or ask room ops with a redacted audit bundle.",
            ],
            "heuristic_only": True,
        }
    if status == 422:
        suffix_note = "Trailing suffix alone often does not bypass normalized comparison."
        if "suffix" in low or "bypass" in low:
            suffix_note = "Question about suffix bypass seen before: heuristic says suffix alone is not enough."
        return {
            "status": 422,
            "category": "duplicate_filter_422",
            "plain_cause": "Duplicate filter for repeated normalized text. Rephrase, do not resend.",
            "detail": suffix_note,
            "should_retry_same_payload": False,
            "safe_next_steps": [
                "Stop resending the same or near-same text.",
                "Rephrase substantially across the body, not just the tail.",
                "Preview normalization offline before any manual retry.",
                "Wait and quench; ask room ops if blocked.",
            ],
            "heuristic_only": True,
        }
    if status == 429:
        return {
            "status": 429,
            "category": "rate_limit_429",
            "plain_cause": "Rate limit. Slow down.",
            "detail": "Back off and quench.",
            "should_retry_same_payload": False,
            "safe_next_steps": [
                "Stop sending for a while.",
                "Do not burst retry.",
            ],
            "heuristic_only": True,
        }
    if status in (200, 201, 204):
        return {
            "status": status,
            "category": "success",
            "plain_cause": "Success.",
            "detail": "No quench needed.",
            "should_retry_same_payload": False,
            "safe_next_steps": ["No action needed."],
            "heuristic_only": True,
        }
    if status in (500, 503):
        return {
            "status": status,
            "category": "server_error",
            "plain_cause": "Server side error. Cautious later retry may be okay.",
            "detail": "Unlike 400 ceiling, this is not an invariant rejection.",
            "should_retry_same_payload": True,
            "safe_next_steps": [
                "Wait, then try once later.",
                "Quench if it repeats.",
            ],
            "heuristic_only": True,
        }
    return {
        "status": status,
        "category": "unknown",
        "plain_cause": "Unrecognized code. Treat as unknown and ask room ops.",
        "detail": message[:120],
        "should_retry_same_payload": False,
        "safe_next_steps": [
            "Do not loop retries.",
            "Save the message and ask room ops.",
        ],
        "heuristic_only": True,
    }


def parse_log_lines(lines):
    """Extract status codes from pasted log lines. No file access."""
    if not isinstance(lines, list):
        raise TypeError("lines must be a list")
    out = []
    for line in lines:
        if not isinstance(line, str):
            raise TypeError("each line must be str")
        m = _STATUS_RE.search(line)
        found = int(m.group(1)) if m else None
        out.append({
            "line": line[:200],
            "status": found,
        })
    return out


def _status_of(item):
    if isinstance(item, int):
        return item
    if isinstance(item, dict):
        v = item.get("status")
        if isinstance(v, int):
            return v
        return None
    return None


def plan_quench(statuses):
    """Count 400s and 422s and recommend stop, wait, rephrase."""
    if not isinstance(statuses, list):
        raise TypeError("statuses must be a list")
    codes = []
    for s in statuses:
        v = _status_of(s)
        if v is None and isinstance(s, str):
            m = _STATUS_RE.search(s)
            if m:
                v = int(m.group(1))
        if isinstance(v, int):
            codes.append(v)
    total_400 = 0
    total_422 = 0
    for c in codes:
        if c == 400:
            total_400 += 1
        if c == 422:
            total_422 += 1
    tail_400 = 0
    tail_422 = 0
    for c in reversed(codes):
        if c == 400 and tail_422 == 0:
            tail_400 += 1
        elif c == 422 and tail_400 == 0:
            tail_422 += 1
        else:
            break
    if not codes:
        action = "no_data"
        explanation = "No status codes pasted. Nothing to plan."
        wait_hint = "Paste recent codes to get guidance."
        rephrase = False
    elif tail_400 >= STOP_AFTER_400:
        action = "stop"
        explanation = "Consecutive invariant 400s look like a ceiling. Further retries will keep failing."
        wait_hint = "Stop retries for this payload. Review limits and ask ops."
        rephrase = False
    elif tail_422 >= STOP_AFTER_422:
        action = "stop_and_rephrase"
        explanation = "Consecutive 422s look like duplicate filter. Suffix tweaks are not enough."
        wait_hint = "Quench, wait, then rephrase substantially before any manual retry."
        rephrase = True
    elif tail_400 == 1 and tail_422 == 0:
        action = "stop_and_review"
        explanation = "Single 400 suggests ceiling or validation. Do not retry same payload."
        wait_hint = "Review payload against limits."
        rephrase = False
    elif tail_422 == 1:
        action = "rephrase_before_retry"
        explanation = "Single 422 suggests duplicate. Rephrase body before any retry."
        wait_hint = "Wait, rephrase across the body, preview offline."
        rephrase = True
    else:
        action = "proceed_with_caution"
        explanation = "No long 400 or 422 streak at tail. Stay cautious."
        wait_hint = "Send once, then quench on any 400 or 422."
        rephrase = False
    return {
        "total": len(codes),
        "total_400": total_400,
        "total_422": total_422,
        "consecutive_400_tail": tail_400,
        "consecutive_422_tail": tail_422,
        "stop_after_400": STOP_AFTER_400,
        "stop_after_422": STOP_AFTER_422,
        "action": action,
        "rephrase_required": rephrase,
        "wait_hint": wait_hint,
        "explanation": explanation,
        "heuristic_only": True,
    }


def build_audit_bundle(entries, room="technocore"):
    """Build redacted bundle with hashes only, never raw payloads."""
    if not isinstance(entries, list):
        raise TypeError("entries must be a list")
    if not isinstance(room, str):
        raise TypeError("room must be str")
    items = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            raise TypeError("each entry must be a dict")
        payload = e.get("payload", "")
        status = e.get("status")
        seq = e.get("seq", 0)
        msg = e.get("message", "")
        entry_room = e.get("room", room)
        if not isinstance(payload, str):
            raise TypeError("payload must be str")
        if not isinstance(msg, str):
            msg = ""
        if not isinstance(seq, int):
            seq = 0
        if not isinstance(status, int):
            status = 0
        if not isinstance(entry_room, str):
            entry_room = room
        norm = normalize_text(payload)
        full = hash_text(payload)
        nhash = hash_text(norm)
        items.append({
            "index": i,
            "room": entry_room,
            "seq": seq,
            "status": status,
            "payload_hash_full": full,
            "payload_hash_short": full[:16],
            "normalized_hash_short": nhash[:16],
            "normalization_version": NORMALIZATION_VERSION,
            "message_hint": msg[:80],
        })
    return {
        "room": room,
        "count": len(items),
        "normalization_version": NORMALIZATION_VERSION,
        "heuristic_only": True,
        "items": items,
    }


def bundle_to_json(bundle):
    """Serialize audit bundle to sorted JSON string."""
    return json.dumps(bundle, indent=2, sort_keys=True)


def docs_gap_report(observed, documented=None, room="technocore"):
    """Draft markdown comparing observed vs documented behavior."""
    if not isinstance(observed, list):
        raise TypeError("observed must be a list")
    if documented is None:
        documented = DOCUMENTED_BEHAVIOR
    if not isinstance(documented, str):
        raise TypeError("documented must be str")
    if not isinstance(room, str):
        raise TypeError("room must be str")
    lines = []
    lines.append("# Docs-gap report for room ops")
    lines.append("")
    lines.append("Room: " + room)
    lines.append("")
    lines.append("Heuristic only. Needs human review before any resend.")
    lines.append("")
    lines.append("## Observed behavior")
    lines.append("")
    if not observed:
        lines.append("- (no observations pasted)")
    else:
        for note in observed:
            if not isinstance(note, str):
                raise TypeError("each observation must be str")
            clean = note.strip()
            if clean:
                lines.append("- " + clean)
    lines.append("")
    lines.append("## Documented behavior")
    lines.append("")
    lines.append(documented.strip())
    lines.append("")
    lines.append("## Gap")
    lines.append("")
    lines.append("Server docs omit duplicate-filter normalization rules, suffix handling, and 400 vs 422 distinction.")
    lines.append("")
    lines.append("## Questions for ops")
    lines.append("")
    lines.append("- Does the 422 filter compare raw text or canonicalized form?")
    lines.append("- Does a trailing random suffix bypass dedupe, or is rephrasing required?")
    lines.append("- When should clients stop retries after invariant 400 ceiling?")
    lines.append("")
    lines.append("## Attachments")
    lines.append("")
    lines.append("Attach redacted audit bundle JSON (hashes only) with room and seq references.")
    lines.append("")
    return "\n".join(lines) + "\n"
