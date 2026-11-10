#!/usr/bin/env python3
"""Offline consistency checks for an explicitly supplied CRM sales handoff."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

VERSION = "0.1.0"
MAX_INPUT_BYTES = 1024 * 1024
MAX_HANDOFFS = 500
MAX_DEALS = 2000
ALGORITHM = "sha256/json-sort-keys-ensure-ascii-compact-v1"
BASIS = "supplied_local_snapshot_and_receipt_fields_only"
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
STAMP_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"


def _string(maximum, **extra):
    return dict({"type": "string", "minLength": 1, "maxLength": maximum}, **extra)


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


_ID = _string(80, pattern=ID_PATTERN)
_TIME = _string(40, pattern=STAMP_PATTERN, format="date-time")
_DEAL = _object({"deal_id": _ID, "owner_id": _ID, "stage": _ID})
_EVIDENCE = _object({"id": _ID, "source_ref": _string(500), "summary": _string(2000)})
_HANDOFF = _object({
    "id": _ID, "deal_id": _ID, "from_owner_id": _ID, "to_owner_id": _ID,
    "target_stage": _ID, "prepared_at": _TIME,
    "next_step": _object({"description": _string(2000), "due_at": _TIME}),
    "evidence": {"type": "array", "minItems": 1, "maxItems": 20, "items": _EVIDENCE},
})
_ACK = _object({
    "handoff_id": _ID, "accepted_by": _ID, "accepted_at": _TIME,
    "decision": {"type": "string", "enum": ["accepted", "rejected"]},
    "packet_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "note": {"type": "string", "maxLength": 2000},
})
INPUT_SCHEMA = dict(_object({
    "schema_version": {"type": "integer", "const": 1},
    "as_of": _TIME,
    "max_snapshot_age_hours": {"type": "integer", "minimum": 1, "maximum": 168},
    "snapshot": _object({
        "captured_at": _TIME, "complete": {"type": "boolean"},
        "deals": {"type": "array", "maxItems": MAX_DEALS, "items": _DEAL},
    }),
    "handoffs": {"type": "array", "minItems": 1, "maxItems": MAX_HANDOFFS, "items": _HANDOFF},
    "acknowledgements": {"type": "array", "maxItems": MAX_HANDOFFS, "items": _ACK},
}), **{"$schema": "https://json-schema.org/draft/2020-12/schema",
       "title": "CRM RevOps Kit handoff input v1",
       "description": "Additional semantic checks enforce unique IDs, receipt references, distinct owners, due_at after prepared_at, valid timezone-aware timestamps and control-free strings. Completeness and signer identity remain supplied declarations. Raw UTF-8 input is limited to 1 MiB."})

FINDING_ORDER = (
    "SNAPSHOT_INCOMPLETE", "SNAPSHOT_STALE", "SNAPSHOT_FUTURE",
    "SNAPSHOT_BEFORE_HANDOFF", "SNAPSHOT_BEFORE_ACK", "DEAL_NOT_IN_SNAPSHOT",
    "OWNER_MISMATCH", "STAGE_MISMATCH", "PACKET_FUTURE", "NEXT_STEP_OVERDUE",
    "ACK_MISSING", "ACK_REJECTED", "ACK_HASH_MISMATCH", "ACK_ACTOR_MISMATCH",
    "ACK_BEFORE_PACKET", "ACK_FUTURE",
)


class InputError(Exception):
    """A public, payload-free error code."""


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def packet_sha256(packet):
    return hashlib.sha256(canonical_bytes(packet)).hexdigest()


def timestamp(value):
    if (not isinstance(value, str) or not re.fullmatch(STAMP_PATTERN, value)
            or value.endswith("-00:00")):
        raise InputError("TIMESTAMP_INVALID")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        return parsed.astimezone(dt.timezone.utc)
    except (ValueError, OverflowError):
        raise InputError("TIMESTAMP_INVALID")


def text(value, maximum, allow_empty=False):
    if not isinstance(value, str) or len(value) > maximum:
        raise InputError("STRING_INVALID")
    if (not allow_empty and not value.strip()) or any(unicodedata.category(c) in ("Cc", "Cs") for c in value):
        raise InputError("STRING_INVALID")


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(ID_PATTERN, value):
        raise InputError("IDENTIFIER_INVALID")


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise InputError("OBJECT_FIELDS_INVALID")


def collection(value, maximum, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise InputError("COLLECTION_INVALID")


def unique(rows, key):
    values = [row[key] for row in rows]
    if len(values) != len(set(values)):
        raise InputError("DUPLICATE_ID")


def validate(document):
    """Validate the full exact shape and relational constraints; return unchanged input."""
    exact(document, ("schema_version", "as_of", "max_snapshot_age_hours", "snapshot", "handoffs", "acknowledgements"))
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise InputError("SCHEMA_VERSION_INVALID")
    timestamp(document["as_of"])
    age = document["max_snapshot_age_hours"]
    if type(age) is not int or not 1 <= age <= 168:
        raise InputError("MAX_AGE_INVALID")
    snapshot = document["snapshot"]
    exact(snapshot, ("captured_at", "complete", "deals"))
    timestamp(snapshot["captured_at"])
    if type(snapshot["complete"]) is not bool:
        raise InputError("COMPLETENESS_INVALID")
    collection(snapshot["deals"], MAX_DEALS)
    for deal in snapshot["deals"]:
        exact(deal, ("deal_id", "owner_id", "stage"))
        for value in deal.values():
            identifier(value)
    unique(snapshot["deals"], "deal_id")
    collection(document["handoffs"], MAX_HANDOFFS, 1)
    for packet in document["handoffs"]:
        exact(packet, ("id", "deal_id", "from_owner_id", "to_owner_id", "target_stage", "prepared_at", "next_step", "evidence"))
        for key in ("id", "deal_id", "from_owner_id", "to_owner_id", "target_stage"):
            identifier(packet[key])
        if packet["from_owner_id"] == packet["to_owner_id"]:
            raise InputError("OWNERS_MUST_DIFFER")
        prepared = timestamp(packet["prepared_at"])
        step = packet["next_step"]
        exact(step, ("description", "due_at"))
        text(step["description"], 2000)
        if timestamp(step["due_at"]) <= prepared:
            raise InputError("DUE_NOT_AFTER_PACKET")
        collection(packet["evidence"], 20, 1)
        for evidence in packet["evidence"]:
            exact(evidence, ("id", "source_ref", "summary"))
            identifier(evidence["id"])
            text(evidence["source_ref"], 500)
            text(evidence["summary"], 2000)
        unique(packet["evidence"], "id")
    unique(document["handoffs"], "id")
    unique(document["handoffs"], "deal_id")
    collection(document["acknowledgements"], MAX_HANDOFFS)
    packet_ids = {packet["id"] for packet in document["handoffs"]}
    for ack in document["acknowledgements"]:
        exact(ack, ("handoff_id", "accepted_by", "accepted_at", "decision", "packet_sha256", "note"))
        identifier(ack["handoff_id"])
        identifier(ack["accepted_by"])
        timestamp(ack["accepted_at"])
        if ack["handoff_id"] not in packet_ids:
            raise InputError("ACK_HANDOFF_UNKNOWN")
        if ack["decision"] not in ("accepted", "rejected") or not isinstance(ack["decision"], str):
            raise InputError("ACK_DECISION_INVALID")
        if not isinstance(ack["packet_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", ack["packet_sha256"]):
            raise InputError("ACK_HASH_INVALID")
        text(ack["note"], 2000, allow_empty=True)
    unique(document["acknowledgements"], "handoff_id")
    return document


def _pairs(rows):
    value = {}
    for key, item in rows:
        if key in value:
            raise InputError("DUPLICATE_JSON_KEY")
        value[key] = item
    return value


def _constant(unused):
    raise InputError("NONFINITE_JSON")


def parse_input(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_INPUT_BYTES:
        raise InputError("INPUT_TOO_LARGE")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError):
        raise InputError("JSON_INVALID")
    return validate(value)


def load_input(path):
    try:
        if not Path(path).is_file():
            raise InputError("INPUT_READ_ERROR")
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
    except (OSError, ValueError):
        raise InputError("INPUT_READ_ERROR")
    return parse_input(raw), hashlib.sha256(raw).hexdigest()


def fingerprint(document, input_sha256):
    validate(document)
    return {"ok": True, "command": "fingerprint", "version": VERSION,
            "algorithm": ALGORITHM, "input_sha256": input_sha256,
            "packets": [{"handoff_id": packet["id"],
                         "canonical_json": canonical_bytes(packet).decode("ascii"),
                         "packet_sha256": packet_sha256(packet)} for packet in document["handoffs"]]}


def audit(document, input_sha256):
    validate(document)
    as_of = timestamp(document["as_of"])
    snapshot = document["snapshot"]
    captured = timestamp(snapshot["captured_at"])
    global_findings = set()
    if not snapshot["complete"]:
        global_findings.add("SNAPSHOT_INCOMPLETE")
    if captured > as_of:
        global_findings.add("SNAPSHOT_FUTURE")
    if as_of - captured > dt.timedelta(hours=document["max_snapshot_age_hours"]):
        global_findings.add("SNAPSHOT_STALE")
    deals = {row["deal_id"]: row for row in snapshot["deals"]}
    acks = {row["handoff_id"]: row for row in document["acknowledgements"]}
    rows = []
    for packet in document["handoffs"]:
        findings = set(global_findings)
        prepared = timestamp(packet["prepared_at"])
        if captured < prepared:
            findings.add("SNAPSHOT_BEFORE_HANDOFF")
        if prepared > as_of:
            findings.add("PACKET_FUTURE")
        if timestamp(packet["next_step"]["due_at"]) < as_of:
            findings.add("NEXT_STEP_OVERDUE")
        ack = acks.get(packet["id"])
        if ack is None:
            findings.add("ACK_MISSING")
        else:
            accepted = timestamp(ack["accepted_at"])
            if accepted > as_of:
                findings.add("ACK_FUTURE")
            if accepted < prepared:
                findings.add("ACK_BEFORE_PACKET")
            if captured < accepted:
                findings.add("SNAPSHOT_BEFORE_ACK")
            if ack["decision"] != "accepted":
                findings.add("ACK_REJECTED")
            if ack["packet_sha256"] != packet_sha256(packet):
                findings.add("ACK_HASH_MISMATCH")
            if ack["accepted_by"] != packet["to_owner_id"]:
                findings.add("ACK_ACTOR_MISMATCH")
        deal = deals.get(packet["deal_id"])
        if deal is None:
            findings.add("DEAL_NOT_IN_SNAPSHOT")
        # An unusable snapshot cannot assert present ownership or stage.
        usable_snapshot = not (global_findings or captured < prepared or
                               (ack is not None and captured < timestamp(ack["accepted_at"])))
        if deal is not None and usable_snapshot:
            if deal["owner_id"] != packet["to_owner_id"]:
                findings.add("OWNER_MISMATCH")
            if deal["stage"] != packet["target_stage"]:
                findings.add("STAGE_MISMATCH")
        rows.append({"handoff_id": packet["id"], "deal_id": packet["deal_id"],
                     "packet_sha256": packet_sha256(packet),
                     "classification": "needs_review" if findings else "consistent",
                     "findings": [code for code in FINDING_ORDER if code in findings]})
    consistent = sum(row["classification"] == "consistent" for row in rows)
    return {"ok": True, "command": "audit", "version": VERSION, "evidence_basis": BASIS,
            "as_of": document["as_of"], "input_sha256": input_sha256,
            "snapshot": {"captured_at": snapshot["captured_at"], "complete": snapshot["complete"],
                         "max_age_hours": document["max_snapshot_age_hours"]},
            "summary": {"handoffs": len(rows), "consistent": consistent, "needs_review": len(rows) - consistent},
            "rows": rows}


def output_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode("ascii")


def write_output(path, value, replace=False, input_path=None):
    """Atomically publish a bounded report; never overwrite an input or symlink."""
    target = Path(os.path.abspath(str(path)))
    for part in (target,) + tuple(target.parents):
        if part.is_symlink():
            raise InputError("OUTPUT_SYMLINK_REFUSED")
    if input_path is not None:
        original = Path(input_path)
        try:
            collision = target.resolve() == original.resolve() or (target.exists() and os.path.samefile(str(target), str(original)))
        except OSError:
            raise InputError("OUTPUT_IO_ERROR")
        if collision:
            raise InputError("OUTPUT_IS_INPUT")
    if target.exists() and not replace:
        raise InputError("OUTPUT_EXISTS")
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".crm-revops-report-", dir=str(target.parent))
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(output_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, str(target))
        else:
            os.link(temporary, str(target))
    except OSError:
        raise InputError("OUTPUT_IO_ERROR")
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def onboard():
    marker = Path(__file__).resolve().parent / ".onboarded"
    if marker.is_symlink():
        raise InputError("ONBOARD_MARKER_INVALID")
    if marker.exists():
        if (not marker.is_file() or marker.stat().st_size != len(VERSION) + 1
                or marker.read_bytes() != (VERSION + "\n").encode("ascii")):
            raise InputError("ONBOARD_MARKER_INVALID")
        return {"ok": True, "command": "onboard", "version": VERSION, "already_shown": True}
    descriptor = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write((VERSION + "\n").encode("ascii"))
    return {"ok": True, "command": "onboard", "version": VERSION, "already_shown": False,
            "author": "Дмитрий Лукашов / Dmitry Lukashov",
            "message": "Start with the invented demo. A consistent packet is not verified human acceptance or a live CRM readback.",
            "practical_notes": "https://t.me/lookatsoul",
            "learn": "https://lookatshow.ru/executive?utm_source=github&utm_medium=open_module&utm_campaign=crm-revops-kit&utm_content=onboard_learn",
            "implementation": "https://lookatshow.ru/ai-implementation/?utm_source=github&utm_medium=open_module&utm_campaign=crm-revops-kit&utm_content=onboard_implementation"}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError("CLI_USAGE")


def main(argv=None):
    try:
        parser = Parser(description="Audit supplied CRM handoff packets, exact receipt hashes and snapshot fields offline.")
        parser.add_argument("--json", action="store_true", help="Return lossless machine-readable JSON (also the default).")
        sub = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
        for name in ("doctor", "schema", "demo", "onboard"):
            sub.add_parser(name)
        sub.add_parser("fingerprint").add_argument("input")
        audit_parser = sub.add_parser("audit")
        audit_parser.add_argument("input")
        audit_parser.add_argument("--output")
        audit_parser.add_argument("--replace", action="store_true")
        args = parser.parse_args(argv)
        if sys.version_info < (3, 9):
            raise InputError("PYTHON_VERSION")
        status = 0
        if args.command == "doctor":
            fixture = Path(__file__).resolve().parent / "examples/synthetic-handoffs.json"
            load_input(fixture)
            result = {"ok": True, "command": "doctor", "version": VERSION,
                      "python": ".".join(str(n) for n in sys.version_info[:3]),
                      "offline": True, "network_required": False, "auth_required": False,
                      "runtime_dependencies": "Python 3.9+ standard library",
                      "synthetic_fixture_found": True, "posix_installer": os.name == "posix"}
        elif args.command == "schema":
            result = {"ok": True, "command": "schema", "version": VERSION, "input_schema": INPUT_SCHEMA,
                      "max_input_bytes": MAX_INPUT_BYTES, "finding_codes": list(FINDING_ORDER),
                      "fingerprint_algorithm": ALGORITHM, "evidence_basis": BASIS}
        elif args.command == "onboard":
            result = onboard()
        else:
            path = Path(__file__).resolve().parent / "examples/synthetic-handoffs.json" if args.command == "demo" else Path(args.input)
            document, source_sha = load_input(path)
            if args.command == "fingerprint":
                result = fingerprint(document, source_sha)
            else:
                result = audit(document, source_sha)
                status = 1 if result["summary"]["needs_review"] else 0
                if args.command == "demo":
                    result.update(command="demo", synthetic=True)
                else:
                    if args.replace and not args.output:
                        raise InputError("CLI_USAGE")
                    if args.output:
                        write_output(args.output, result, args.replace, path)
        sys.stdout.write(output_bytes(result).decode("ascii"))
        return status
    except (InputError, OSError, ValueError, TypeError, RecursionError, OverflowError) as error:
        code = str(error) if isinstance(error, InputError) else "OPERATION_REFUSED"
        sys.stdout.write(output_bytes({"ok": False, "error": {"code": code,
            "message": "Input, command or output was refused. Check schema/help; supplied payloads are not included in errors."}}).decode("ascii"))
        return 2


if __name__ == "__main__":
    sys.exit(main())
