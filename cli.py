"""Command line wrapper for helper.py. Offline only, no network."""
import argparse
import json
import sys
import helper


def build_parser():
    p = argparse.ArgumentParser(
        description="Technocore 400 vs 422 clarity and quench helper (offline, heuristic only)"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("interpret", help="explain a status code")
    a.add_argument("--status", type=int, required=True)
    a.add_argument("--message", default="")

    b = sub.add_parser("preview", help="preview normalization")
    b.add_argument("--original", default="")
    b.add_argument("--candidate", default="")

    c = sub.add_parser("quench", help="plan quench from statuses")
    c.add_argument("--statuses", default="", help="comma separated, e.g. 422,422,400")

    d = sub.add_parser("audit", help="build redacted audit bundle for one entry")
    d.add_argument("--room", default="technocore")
    d.add_argument("--status", type=int, default=422)
    d.add_argument("--seq", type=int, default=0)
    d.add_argument("--payload", default="")
    d.add_argument("--message", default="")

    e = sub.add_parser("gap", help="draft docs-gap report")
    e.add_argument("--observed", default="", help="semicolon separated notes")
    e.add_argument("--documented", default="")
    e.add_argument("--room", default="technocore")
    return p


def parse_status_list(text):
    out = []
    text = (text or "").strip()
    if not text:
        return out
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "interpret":
        result = helper.interpret_status(args.status, args.message)
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.cmd == "preview":
        result = helper.preview_normalization(args.original, args.candidate)
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.cmd == "quench":
        statuses = parse_status_list(args.statuses)
        result = helper.plan_quench(statuses)
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.cmd == "audit":
        entry = {
            "payload": args.payload,
            "status": args.status,
            "seq": args.seq,
            "message": args.message,
            "room": args.room,
        }
        bundle = helper.build_audit_bundle([entry], room=args.room)
        json.dump(bundle, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.cmd == "gap":
        if args.observed.strip():
            observed = [s.strip() for s in args.observed.split(";") if s.strip()]
        else:
            observed = []
        documented = args.documented if args.documented else None
        sys.stdout.write(helper.docs_gap_report(observed, documented, room=args.room))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
