import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("crm_revops_kit", ROOT / "crm_revops_kit.py")
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


def fixture():
    return json.loads((ROOT / "examples/synthetic-handoffs.json").read_text(encoding="utf-8"))


def good():
    doc = fixture()
    doc["handoffs"] = doc["handoffs"][:1]
    doc["acknowledgements"] = doc["acknowledgements"][:1]
    doc["snapshot"]["deals"] = doc["snapshot"]["deals"][:1]
    return doc


def raw(doc):
    return (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def check(doc):
    data = raw(doc)
    return kit.audit(kit.parse_input(data), hashlib.sha256(data).hexdigest())


def codes(doc):
    return check(doc)["rows"][0]["findings"]


def cli(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, "-B", str(ROOT / "crm_revops_kit.py"), "--json", *map(str, args)],
                          cwd=cwd, env=env, capture_output=True, timeout=30)


class ContractTests(unittest.TestCase):
    def test_six_case_demo_expected_outcomes(self):
        result = check(fixture())
        self.assertEqual(result["summary"], {"handoffs": 6, "consistent": 1, "needs_review": 5})
        self.assertEqual([r["findings"] for r in result["rows"]], [[], ["ACK_MISSING"],
            ["ACK_HASH_MISMATCH"], ["OWNER_MISMATCH"], ["NEXT_STEP_OVERDUE"], ["ACK_REJECTED"]])

    def test_consistent_means_only_supplied_fields_agree(self):
        result = check(good())
        self.assertEqual(result["evidence_basis"], "supplied_local_snapshot_and_receipt_fields_only")
        self.assertEqual(result["rows"][0]["classification"], "consistent")
        self.assertNotIn("approved", result)

    def test_fingerprint_spec_and_canonical_bytes(self):
        doc = good(); packet = doc["handoffs"][0]
        expected = json.dumps(packet, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
        result = kit.fingerprint(doc, "0" * 64)
        self.assertEqual(result["algorithm"], "sha256/json-sort-keys-ensure-ascii-compact-v1")
        self.assertEqual(result["packets"][0]["canonical_json"], expected)
        self.assertEqual(result["packets"][0]["packet_sha256"], hashlib.sha256(expected.encode("ascii")).hexdigest())

    def test_packet_hash_ignores_key_order(self):
        packet = good()["handoffs"][0]
        self.assertEqual(kit.packet_sha256(packet), kit.packet_sha256(dict(reversed(list(packet.items())))))

    def test_changed_packet_does_not_match_old_ack(self):
        doc = good(); doc["handoffs"][0]["next_step"]["description"] += " Revised."
        self.assertEqual(codes(doc), ["ACK_HASH_MISMATCH"])

    def test_receipt_and_snapshot_not_in_packet_hash(self):
        doc = good(); packet_hash = kit.packet_sha256(doc["handoffs"][0])
        doc["acknowledgements"][0]["note"] = "New receipt note"
        doc["snapshot"]["complete"] = False
        self.assertEqual(kit.packet_sha256(doc["handoffs"][0]), packet_hash)

    def test_report_input_sha_binds_exact_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"; data = raw(good()); path.write_bytes(data)
            doc, sha = kit.load_input(path)
            self.assertEqual(sha, hashlib.sha256(data).hexdigest())
            path.write_bytes(data + b" ")
            unused, changed = kit.load_input(path)
            self.assertNotEqual(sha, changed)
            self.assertEqual(kit.packet_sha256(doc["handoffs"][0]), kit.packet_sha256(unused["handoffs"][0]))

    def test_incomplete_snapshot_does_not_assert_owner_or_stage(self):
        doc = good(); doc["snapshot"]["complete"] = False
        doc["snapshot"]["deals"][0].update(owner_id="other", stage="other")
        self.assertEqual(codes(doc), ["SNAPSHOT_INCOMPLETE"])

    def test_stale_snapshot_does_not_assert_owner_or_stage(self):
        doc = good(); doc["snapshot"]["captured_at"] = "2026-11-08T08:45:00+03:00"
        doc["snapshot"]["deals"][0].update(owner_id="other", stage="other")
        self.assertIn("SNAPSHOT_STALE", codes(doc)); self.assertNotIn("OWNER_MISMATCH", codes(doc))
        self.assertNotIn("STAGE_MISMATCH", codes(doc))

    def test_future_snapshot_does_not_assert_current_owner_or_stage(self):
        doc = good(); doc["snapshot"]["captured_at"] = "2026-11-10T10:00:00+03:00"
        doc["snapshot"]["deals"][0].update(owner_id="other", stage="other")
        self.assertEqual(codes(doc), ["SNAPSHOT_FUTURE"])

    def test_snapshot_before_packet_requires_review(self):
        doc = good(); doc["snapshot"]["captured_at"] = "2026-11-10T07:59:59+03:00"
        self.assertIn("SNAPSHOT_BEFORE_HANDOFF", codes(doc))

    def test_snapshot_before_acceptance_cannot_establish_post_handoff(self):
        doc = good(); doc["snapshot"]["captured_at"] = "2026-11-10T08:14:59+03:00"
        doc["snapshot"]["deals"][0]["owner_id"] = "other"
        self.assertEqual(codes(doc), ["SNAPSHOT_BEFORE_ACK"])

    def test_missing_deal_is_reported_only_as_not_in_supplied_snapshot(self):
        doc = good(); doc["snapshot"]["deals"] = []
        self.assertEqual(codes(doc), ["DEAL_NOT_IN_SNAPSHOT"])

    def test_snapshot_owner_mismatch(self):
        doc = good(); doc["snapshot"]["deals"][0]["owner_id"] = "other"
        self.assertEqual(codes(doc), ["OWNER_MISMATCH"])

    def test_snapshot_stage_mismatch(self):
        doc = good(); doc["snapshot"]["deals"][0]["stage"] = "proposal"
        self.assertEqual(codes(doc), ["STAGE_MISMATCH"])

    def test_future_packet_never_consistent(self):
        doc = good(); doc["handoffs"][0]["prepared_at"] = "2026-11-10T09:30:00+03:00"
        self.assertIn("PACKET_FUTURE", codes(doc))

    def test_deadline_equal_as_of_not_yet_elapsed(self):
        doc = good(); doc["handoffs"][0]["next_step"]["due_at"] = doc["as_of"]
        doc["acknowledgements"][0]["packet_sha256"] = kit.packet_sha256(doc["handoffs"][0])
        self.assertEqual(codes(doc), [])

    def test_one_second_after_deadline_is_overdue(self):
        doc = good(); doc["handoffs"][0]["next_step"]["due_at"] = "2026-11-10T08:59:59+03:00"
        doc["acknowledgements"][0]["packet_sha256"] = kit.packet_sha256(doc["handoffs"][0])
        self.assertEqual(codes(doc), ["NEXT_STEP_OVERDUE"])

    def test_timezone_equivalent_as_of_keeps_same_findings(self):
        doc = fixture(); expected = [row["findings"] for row in check(doc)["rows"]]
        doc["as_of"] = "2026-11-10T06:00:00Z"
        self.assertEqual([row["findings"] for row in check(doc)["rows"]], expected)

    def test_snapshot_age_boundary_is_inclusive(self):
        doc = good(); doc["snapshot"]["captured_at"] = "2026-11-09T09:00:00+03:00"
        self.assertNotIn("SNAPSHOT_STALE", codes(doc))
        doc["snapshot"]["captured_at"] = "2026-11-09T08:59:59+03:00"
        self.assertIn("SNAPSHOT_STALE", codes(doc))

    def test_missing_ack(self):
        doc = good(); doc["acknowledgements"] = []
        self.assertEqual(codes(doc), ["ACK_MISSING"])

    def test_rejected_ack(self):
        doc = good(); doc["acknowledgements"][0]["decision"] = "rejected"
        self.assertEqual(codes(doc), ["ACK_REJECTED"])

    def test_wrong_ack_actor(self):
        doc = good(); doc["acknowledgements"][0]["accepted_by"] = "another-role"
        self.assertEqual(codes(doc), ["ACK_ACTOR_MISMATCH"])

    def test_ack_before_packet(self):
        doc = good(); doc["acknowledgements"][0]["accepted_at"] = "2026-11-10T07:59:59+03:00"
        self.assertEqual(codes(doc), ["ACK_BEFORE_PACKET"])

    def test_future_ack_not_usable(self):
        doc = good(); doc["acknowledgements"][0]["accepted_at"] = "2026-11-10T09:30:00+03:00"
        self.assertIn("ACK_FUTURE", codes(doc)); self.assertIn("SNAPSHOT_BEFORE_ACK", codes(doc))

    def test_duplicate_keys_rejected_at_every_depth(self):
        for data in [b'{"schema_version":1,"schema_version":1}', b'{"x":{"a":1,"a":2}}']:
            with self.subTest(data=data), self.assertRaises(kit.InputError): kit.parse_input(data)

    def test_nonfinite_and_overflow_numbers_not_valid_input(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e9999"):
            data = raw(good()).replace(b'"max_snapshot_age_hours": 24', ('"max_snapshot_age_hours": '+value).encode())
            with self.subTest(value=value), self.assertRaises(kit.InputError): kit.parse_input(data)

    def test_invalid_utf8_and_json_rejected(self):
        for data in (b"\xff", b"{", b"null", b"[]", b"\xef\xbb\xbf{}"):
            with self.subTest(data=data), self.assertRaises(kit.InputError): kit.parse_input(data)

    def test_deep_malformed_json_rejected(self):
        with self.assertRaises(kit.InputError): kit.parse_input(b"[" * 3000 + b"0" + b"]" * 3000)

    def test_one_mib_limit(self):
        with self.assertRaises(kit.InputError): kit.parse_input(b" " * (kit.MAX_INPUT_BYTES + 1))

    def test_boolean_not_integer(self):
        for key in ("schema_version", "max_snapshot_age_hours"):
            doc = good(); doc[key] = True
            with self.subTest(key=key), self.assertRaises(kit.InputError): check(doc)

    def test_complete_requires_real_boolean(self):
        doc = good(); doc["snapshot"]["complete"] = 1
        with self.assertRaises(kit.InputError): check(doc)

    def test_unexpected_fields_not_silently_ignored(self):
        for location in ("root", "packet", "step", "evidence", "snapshot", "deal", "ack"):
            doc = good(); value = {"root":doc,"packet":doc["handoffs"][0],"step":doc["handoffs"][0]["next_step"],
                "evidence":doc["handoffs"][0]["evidence"][0],"snapshot":doc["snapshot"],
                "deal":doc["snapshot"]["deals"][0],"ack":doc["acknowledgements"][0]}[location]
            value["unexpected"] = "private-value"
            with self.subTest(location=location), self.assertRaises(kit.InputError): check(doc)

    def test_duplicate_domain_ids_rejected(self):
        for location in ("handoffs", "deals", "acks", "evidence"):
            doc = good(); rows = {"handoffs":doc["handoffs"],"deals":doc["snapshot"]["deals"],
                "acks":doc["acknowledgements"],"evidence":doc["handoffs"][0]["evidence"]}[location]
            rows.append(copy.deepcopy(rows[0]))
            with self.subTest(location=location), self.assertRaises(kit.InputError): check(doc)

    def test_two_handoffs_same_deal_rejected(self):
        doc = good(); packet = copy.deepcopy(doc["handoffs"][0]); packet["id"] = "H99"; doc["handoffs"].append(packet)
        with self.assertRaises(kit.InputError): check(doc)

    def test_unknown_ack_handoff_rejected(self):
        doc = good(); doc["acknowledgements"][0]["handoff_id"] = "UNKNOWN"
        with self.assertRaises(kit.InputError): check(doc)

    def test_same_sender_receiver_rejected(self):
        doc = good(); doc["handoffs"][0]["from_owner_id"] = doc["handoffs"][0]["to_owner_id"]
        with self.assertRaises(kit.InputError): check(doc)

    def test_blank_strings_controls_and_surrogates_rejected(self):
        for value in (" ", "text\nnext", "\u0000", "\u0085", "\ud800", "x" * 2001):
            doc = good(); doc["handoffs"][0]["next_step"]["description"] = value
            with self.subTest(value=repr(value)), self.assertRaises(kit.InputError): kit.validate(doc)

    def test_malformed_timestamps_and_unknown_offset_rejected(self):
        for value in ("2026-11-10", "2026-11-10T09:00:00", "2026-13-10T09:00:00Z", "2026-11-10T09:00:00+24:00",
                      "2026-11-10T09:00:00+00:60", "2026-11-10T09:00:00+03:99", "2026-11-10T09:00:00-00:00",
                      "2026-11-10T09:00:60Z", "0001-01-01T00:00:00+23:59"):
            doc = good(); doc["as_of"] = value
            with self.subTest(value=value), self.assertRaises(kit.InputError): check(doc)

    def test_due_must_follow_packet(self):
        doc = good(); doc["handoffs"][0]["next_step"]["due_at"] = doc["handoffs"][0]["prepared_at"]
        with self.assertRaises(kit.InputError): check(doc)

    def test_no_evidence_or_oversized_collections_rejected(self):
        for count in (0, 21):
            doc = good(); doc["handoffs"][0]["evidence"] *= count
            with self.subTest(count=count), self.assertRaises(kit.InputError): check(doc)
        doc = good(); doc["handoffs"] *= 501
        with self.assertRaises(kit.InputError): check(doc)

    def test_declared_age_policy_bounded(self):
        for value in (0, 169, 1.5, "24"):
            doc = good(); doc["max_snapshot_age_hours"] = value
            with self.subTest(value=value), self.assertRaises(kit.InputError): check(doc)

    def test_bad_receipt_hash_and_decision_rejected(self):
        for key, value in (("packet_sha256", "A" * 64), ("packet_sha256", "0" * 63), ("decision", "approved")):
            doc = good(); doc["acknowledgements"][0][key] = value
            with self.subTest(key=key,value=value), self.assertRaises(kit.InputError): check(doc)

    def test_pure_audit_does_not_mutate_input(self):
        doc = fixture(); previous = copy.deepcopy(doc); first = check(doc)
        self.assertEqual(first, check(doc)); self.assertEqual(previous, doc)


class CommandTests(unittest.TestCase):
    def test_doctor_schema_and_demo(self):
        for command, expected in (("doctor",0),("schema",0),("demo",1)):
            result = cli(command)
            self.assertEqual(result.returncode, expected, result.stderr)
            value = json.loads(result.stdout); self.assertTrue(value["ok"])
            if command == "demo": self.assertTrue(value["synthetic"])
            if command == "schema": self.assertEqual(value["input_schema"], kit.INPUT_SCHEMA)

    def test_consistent_cli_exit_zero_and_findings_exit_one(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"input.json"; path.write_bytes(raw(good()))
            self.assertEqual(cli("audit",path).returncode,0)
            path.write_bytes(raw(fixture())); self.assertEqual(cli("audit",path).returncode,1)

    def test_json_errors_do_not_echo_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"bad.json"; path.write_text('{"secret":"NEVER-ECHO-THIS"}',encoding="utf-8")
            result=cli("audit",path)
            self.assertEqual(result.returncode,2); self.assertFalse(json.loads(result.stdout)["ok"])
            self.assertNotIn(b"NEVER-ECHO-THIS", result.stdout+result.stderr)
            self.assertNotIn(b"Traceback", result.stdout+result.stderr)

    def test_cli_usage_errors_are_json(self):
        for args in ([],["unknown"],["audit"],["audit","missing","--replace"]):
            result=cli(*args); self.assertEqual(result.returncode,2); self.assertFalse(json.loads(result.stdout)["ok"])

    def test_cp1252_stdout_preserves_canonical_unicode(self):
        env=dict(os.environ,PYTHONIOENCODING="cp1252")
        result=cli("fingerprint", ROOT/"examples/synthetic-handoffs.json",env=env)
        self.assertEqual(result.returncode,0)
        self.assertTrue(all(c<128 for c in result.stdout))
        packet=json.loads(json.loads(result.stdout)["packets"][0]["canonical_json"])
        self.assertIn("учебный",packet["next_step"]["description"])

    def test_output_same_bytes_as_stdout_no_overwrite_then_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path=root/"input.json"; path.write_bytes(raw(good())); output=root/"report.json"
            result=cli("audit",path,"--output",output)
            self.assertEqual(result.returncode,0); self.assertEqual(result.stdout,output.read_bytes())
            output.write_text("preserve",encoding="utf-8")
            self.assertEqual(cli("audit",path,"--output",output).returncode,2)
            self.assertEqual(output.read_text(encoding="utf-8"),"preserve")
            replaced=cli("audit",path,"--output",output,"--replace")
            self.assertEqual(replaced.returncode,0); self.assertEqual(replaced.stdout,output.read_bytes())

    def test_invalid_input_never_creates_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path=root/"input.json"; path.write_text("{}",encoding="utf-8");output=root/"report.json"
            self.assertEqual(cli("audit",path,"--output",output).returncode,2); self.assertFalse(output.exists())
            output.write_bytes(b"existing report")
            self.assertEqual(cli("audit",path,"--output",output,"--replace").returncode,2)
            self.assertEqual(output.read_bytes(),b"existing report")

    def test_input_output_collision_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory).resolve()/"input.json"; data=raw(good()); path.write_bytes(data)
            result=cli("audit",path,"--output",path,"--replace")
            self.assertEqual(result.returncode,2); self.assertEqual(path.read_bytes(),data)
            self.assertEqual(json.loads(result.stdout)["error"]["code"],"OUTPUT_IS_INPUT")

    @unittest.skipUnless(os.name=="posix","POSIX hardlink/symlink checks")
    def test_hardlink_and_symlink_outputs_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path=root/"input.json"; data=raw(good()); path.write_bytes(data)
            linked=root/"hardlink.json"; os.link(str(path),str(linked))
            result=cli("audit",path,"--output",linked,"--replace")
            self.assertEqual(result.returncode,2)
            self.assertEqual(json.loads(result.stdout)["error"]["code"],"OUTPUT_IS_INPUT")
            symlink=root/"symlink.json"; symlink.symlink_to(path)
            result=cli("audit",path,"--output",symlink,"--replace")
            self.assertEqual(result.returncode,2)
            self.assertEqual(json.loads(result.stdout)["error"]["code"],"OUTPUT_SYMLINK_REFUSED")
            self.assertEqual(path.read_bytes(),data)

    def test_directory_input_is_refused_without_traceback(self):
        result=cli("audit",ROOT)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"],"INPUT_READ_ERROR")

    def test_onboarding_is_optional_once_and_refuses_modified_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory).resolve()/"crm_revops_kit.py"
            script.write_bytes((ROOT/"crm_revops_kit.py").read_bytes())
            args=[sys.executable,"-B",str(script),"--json","onboard"]
            first=subprocess.run(args,capture_output=True,timeout=30)
            second=subprocess.run(args,capture_output=True,timeout=30)
            self.assertEqual(first.returncode,0); self.assertEqual(second.returncode,0)
            self.assertFalse(json.loads(first.stdout)["already_shown"])
            self.assertTrue(json.loads(second.stdout)["already_shown"])
            self.assertNotIn("practical_notes",json.loads(second.stdout))
            marker=script.parent/".onboarded";marker.write_bytes(b"modified")
            changed=subprocess.run(args,capture_output=True,timeout=30)
            self.assertEqual(changed.returncode,2)
            self.assertEqual(marker.read_bytes(),b"modified")

    @unittest.skipUnless(os.name=="posix","POSIX installer only; source CLI tested separately on Windows")
    def test_clean_install_foreign_cwd_and_exact_uninstall_preserves_user_file(self):
        with tempfile.TemporaryDirectory(prefix="crm-revops-install-") as directory:
            root=Path(directory).resolve();prefix=root/"installed";bindir=root/"bin"
            installed=subprocess.run([sys.executable,"-B",str(ROOT/"install.py"),"--prefix",str(prefix),"--bin-dir",str(bindir)],cwd=str(root),capture_output=True,timeout=30)
            self.assertEqual(installed.returncode,0,installed.stdout+installed.stderr)
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PATH=str(bindir)+os.pathsep+os.environ.get("PATH",""))
            result=subprocess.run(["crm-revops-kit","--json","demo"],cwd=str(root),env=env,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,1); self.assertEqual(json.loads(result.stdout)["summary"],{"handoffs":6,"consistent":1,"needs_review":5})
            userfile=prefix/"my-notes.txt";userfile.write_text("keep",encoding="utf-8")
            removed=subprocess.run([sys.executable,"-B",str(prefix/"uninstall.py"),"--prefix",str(prefix),"--bin-dir",str(bindir)],cwd=str(root),env=env,capture_output=True,timeout=30)
            self.assertEqual(removed.returncode,0,removed.stdout+removed.stderr)
            self.assertEqual(userfile.read_text(encoding="utf-8"),"keep");self.assertFalse((bindir/"crm-revops-kit").exists())

    @unittest.skipUnless(os.name=="posix","POSIX installer only")
    def test_install_refuses_existing_and_uninstall_refuses_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();prefix=root/"installed";bindir=root/"bin"
            args=[sys.executable,"-B",str(ROOT/"install.py"),"--prefix",str(prefix),"--bin-dir",str(bindir)]
            self.assertEqual(subprocess.run(args,capture_output=True,timeout=30).returncode,0)
            self.assertEqual(subprocess.run(args,capture_output=True,timeout=30).returncode,2)
            script=prefix/"crm_revops_kit.py";script.write_bytes(script.read_bytes()+b"\n# own change\n")
            result=subprocess.run([sys.executable,"-B",str(prefix/"uninstall.py"),"--prefix",str(prefix),"--bin-dir",str(bindir)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,2);self.assertTrue(script.exists());self.assertTrue((bindir/"crm-revops-kit").exists())


if __name__ == "__main__":
    unittest.main()
