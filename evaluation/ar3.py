"""Source-only document evidence preparation and exact-request offline replay. No live client."""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
from importlib.metadata import version
from pathlib import Path

from archon.adapters.inbound import LocalReader, UnreadablePost, original_message, read_email
from archon.domain.documents import Receipt, SalesInvoice
from archon.security.sanitizer import sanitize_payload

from .ar2 import ROOT, encoded, git, sha256
from .public_workflow import offline_only

PREREGISTRATION = "30094643a0e423e936d6415dd48569061e2f6878"
PINS = {
    "protocol.json": "d62375bff7a023b87a252be32c2b3168ac6048cd2c0f7d7e77d0ae0791ff43d5",
    "inputs.json": "ee6dc03a6a45000d5f9aee4861a00652e66fb13e4bcd91a7ff15584b6a6f3590",
    "gold.json": "43b2ef3bbab1539acb636e785beef7d01249cf80280cbf72775e86cb67dac627",
}
DATA = ROOT / "evaluation/ar3_data"
INVOICE_FIELDS = ("doc_id", "issued", "due", "net", "vat", "gross")
RECEIPT_FIELDS = ("settles", "issued", "amount")
ALLOWED = set(INVOICE_FIELDS + RECEIPT_FIELDS) | {
    "kind", "counterparty", "counterparty_email", "source_ref", "revision", "source_sha256",
    "citations", "transfer_id",
}


class InvalidResponse(ValueError):
    """Malformed or unsupported evidence is not a successful abstention."""


class EvidenceWriteError(RuntimeError):
    """A failed durable checkpoint stops execution, never permits another adapter call."""


class Journal:
    """Create-only, fsynced checkpoints; unfinished runs remain inspectable, never successful."""
    def __init__(self, output, inputs, methods):
        self.output = output
        output.mkdir(parents=True, exist_ok=False)
        self.write("run.json", encoded({"status": "OPEN_JOURNAL",
                   "completion_requires": "result.json and verified SHA256SUMS",
                   "methods": methods, "planned_per_method": 12}))
        for method in methods:
            for index, case in enumerate(inputs):
                self.write(f"journal/{method}/{index:02d}/00-unrun.json", encoded({
                    "case_id": case["id"], "status": "unrun", "attempt": 1,
                    "source_ref": case["source_ref"], "revision": case["revision"],
                    "raw_source_sha256": sha256(case["body"].encode())}))

    def write(self, name, data):
        path = self.output / name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise EvidenceWriteError(f"Checkpoint failed: {name}") from exc

    def slot(self, method, index):
        def checkpoint(name, value):
            data = value.encode() if name == "03-response.txt" else encoded(value)
            self.write(f"journal/{method}/{index:02d}/{name}", data)
        return checkpoint

    def finalize(self, result):
        self.write("result.json", encoded(result))
        entries = sorted(p for p in self.output.rglob("*") if p.is_file())
        self.write("SHA256SUMS", "".join(
            f"{sha256(p.read_bytes())}  {p.relative_to(self.output).as_posix()}\n"
            for p in entries).encode())


def strict_json(raw: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InvalidResponse("Duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(value):
        raise InvalidResponse("Nonfinite JSON number")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, TypeError) as exc:
        raise InvalidResponse(str(exc)) from exc


def load_frozen():
    values = {}
    for name, digest in PINS.items():
        data = (DATA / name).read_bytes()
        if sha256(data) != digest:
            raise ValueError(f"Frozen bytes changed: {name}")
        values[name] = strict_json(data.decode())
    inputs, gold = values["inputs.json"], values["gold.json"]
    if len(inputs) != 12 or [x["id"] for x in inputs] != list(gold):
        raise ValueError("Frozen twelve-case order/denominator changed")
    if sum(value is not None for value in gold.values()) != 6:
        raise ValueError("Frozen positive denominator changed")
    return values["protocol.json"], inputs, gold


def source_view(case):
    text = sanitize_payload(original_message(case["body"])).sanitized_text
    return {"source_ref": case["source_ref"], "revision": case["revision"],
            "source_sha256": sha256(text.encode()), "text": text}


def cited_request(request, view, protocol):
    request = copy.deepcopy(request)
    identity = {key: view[key] for key in ("source_ref", "revision", "source_sha256")}
    request["messages"][0]["content"][0]["text"] += (
        "\n\nEVALUATION-ONLY CITATION CONTRACT (not production functionality):\n"
        + protocol["citation_contract"] + "\n" + protocol["response_contract"]
        + "\nCurrent source identity: " + json.dumps(identity, sort_keys=True)
    )
    return request


def required_fields(fields):
    if fields.get("kind") in {"sales_invoice", "purchase_invoice"}:
        return INVOICE_FIELDS
    if fields.get("kind") == "receipt":
        return RECEIPT_FIELDS
    raise InvalidResponse("Unsupported document kind")


def envelope(fields):
    return {"output": {"message": {"content": [{"text": json.dumps(fields)}]}},
            "stopReason": "end_turn"}


def add_literal_citations(fields, view):
    """Baseline-only literal lookup. No gold, semantic validation or extraction tuning."""
    fields = copy.deepcopy(fields)
    if fields.get("kind") is None:
        return {"kind": None}
    required = required_fields(fields)
    if any(not isinstance(fields.get(key), str) or not fields[key] for key in required):
        return {"kind": None}
    citations = {}
    for key in required:
        start = view["text"].find(fields[key])
        if start < 0:
            return {"kind": None}
        citations[key] = {"start": start, "end": start + len(fields[key]), "quote": fields[key]}
    return {**fields, **{k: view[k] for k in ("source_ref", "revision", "source_sha256")},
            "citations": citations}


def baseline(request, view):
    response = LocalReader().converse(**request)
    fields = strict_json(response["output"]["message"]["content"][0]["text"])
    return encoded(envelope(add_literal_citations(fields, view))).decode()


def validate_response(raw, view):
    response = strict_json(raw)
    try:
        if response.get("stopReason") not in {"end_turn", "stop_sequence"}:
            raise InvalidResponse("Incomplete or unsafe stop reason")
        blocks = response["output"]["message"]["content"]
        if len(blocks) != 1 or set(blocks[0]) != {"text"}:
            raise InvalidResponse("Exactly one text block, no tool use, required")
        fields = strict_json(blocks[0]["text"])
        if not isinstance(fields, dict) or "kind" not in fields or set(fields) - ALLOWED:
            raise InvalidResponse("Unknown action/field or missing kind")
        if fields["kind"] is None:
            if any(value is not None for key, value in fields.items() if key != "kind"):
                raise InvalidResponse("Abstention carries contradictory fields")
            return response, fields
        for key in ("source_ref", "revision", "source_sha256"):
            if type(fields.get(key)) is not type(view[key]) or fields[key] != view[key]:
                raise InvalidResponse(f"Wrong/stale source identity: {key}")
        required = required_fields(fields)
        if set(fields["citations"]) != set(required):
            raise InvalidResponse("Missing/extra field citations")
        for key in required:
            citation = fields["citations"][key]
            if set(citation) != {"start", "end", "quote"}:
                raise InvalidResponse("Malformed citation")
            start, end, quote = citation["start"], citation["end"], citation["quote"]
            if (type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(view["text"])
                    or not isinstance(fields[key], str) or not fields[key]
                    or quote != view["text"][start:end] or quote != fields[key]):
                raise InvalidResponse(f"Wrong/empty/out-of-range field citation: {key}")
        return response, fields
    except (KeyError, TypeError, AttributeError) as exc:
        raise InvalidResponse("Malformed response envelope") from exc


class ObservedClient:
    def __init__(self, adapter, view, protocol, checkpoint=None):
        self.adapter, self.view, self.protocol = adapter, view, protocol
        self.checkpoint = checkpoint
        self.request = self.raw_response = self.response = self.fields = None

    def converse(self, **kwargs):
        if self.request is not None:
            raise RuntimeError("Only one attempt; retries forbidden")
        self.request = cited_request(kwargs, self.view, self.protocol)
        if self.checkpoint:
            self.checkpoint("02-request.json", self.request)
        self.raw_response = self.adapter(copy.deepcopy(self.request), copy.deepcopy(self.view))
        if self.checkpoint:
            self.checkpoint("03-response.txt", self.raw_response)
        self.response, self.fields = validate_response(self.raw_response, self.view)
        return self.response


def projection(document):
    if isinstance(document, Receipt):
        return {"kind": "receipt", "issued": str(document.received_on),
                "settles": document.settles, "amount": str(document.amount),
                "transfer_id": document.transfer_id}
    return {"kind": "sales_invoice" if isinstance(document, SalesInvoice) else "purchase_invoice",
            **{key: str(getattr(document, key)) for key in INVOICE_FIELDS},
            "counterparty_email": getattr(document, "client_email", None)}


def observe(case, protocol, adapter, checkpoint=None):
    view = source_view(case)
    client = ObservedClient(adapter, view, protocol, checkpoint)
    row = {"case_id": case["id"], "attempt": 1, "source_ref": case["source_ref"],
           "revision": case["revision"], "raw_source_sha256": sha256(case["body"].encode()),
           "sanitized_source_sha256": view["source_sha256"], "document": None, "error": None}
    if checkpoint:
        checkpoint("01-started.json", {**row, "status": "started_call_not_confirmed"})
    try:
        document = read_email(case["body"], case["source_ref"], client=client,
                              model_id=protocol["model_request"]["model_id"],
                              **protocol["context"]).document
        row.update(status="document", document=projection(document))
    except UnreadablePost as exc:
        row.update(status="abstained", guard_reason=str(exc))
    except InvalidResponse as exc:
        row.update(status="invalid_response", error=str(exc))
    except EvidenceWriteError:
        raise
    except Exception as exc:
        row.update(status="execution_error", error=f"{type(exc).__name__}: {exc}")
    row.update(request=client.request, request_sha256=sha256(encoded(client.request)),
               raw_response=client.raw_response,
               response_sha256=(sha256(client.raw_response.encode())
                                if isinstance(client.raw_response, str) else None),
               usage=(client.response or {}).get("usage"), model_cost_usd=None,
               cost_status="UNKNOWN_NOT_MEASURED")
    if checkpoint:
        checkpoint("04-result.json", row)
    return row


def score(rows, gold):
    complete = len(rows) == 12 and [r["case_id"] for r in rows] == list(gold)
    captures = sum(r["status"] == "document" and r["document"] == gold[r["case_id"]]
                   for r in rows)
    false_positive = sum(r["status"] == "document" and gold[r["case_id"]] is None
                         for r in rows)
    wrong = sum(r["status"] == "document" and gold[r["case_id"]] is not None
                and r["document"] != gold[r["case_id"]] for r in rows)
    correct_abstentions = sum(r["status"] == "abstained" and gold[r["case_id"]] is None
                             for r in rows)
    counts = {status: sum(r["status"] == status for r in rows)
              for status in ("document", "abstained", "invalid_response", "execution_error")}
    return {"planned": 12, "retained": len(rows), "positive_opportunities": 6,
            "negative_opportunities": 6, "exact_captures": captures, "capture_rate": captures / 6,
            "missed_or_wrong_opportunities": 6 - captures, "false_positives": false_positive,
            "false_positive_rate": false_positive / 6, "wrong_captures": wrong,
            "correct_abstentions": correct_abstentions, "statuses": counts,
            "cohort_complete": complete,
            "contract": "PASS" if complete and captures == 6 and correct_abstentions == 6
            and counts["invalid_response"] == 0 and counts["execution_error"] == 0 else "FAIL"}


def evaluate(inputs, gold, protocol, adapter, journal=None, method=None):
    with offline_only():
        rows = [observe(case, protocol, adapter,
                        journal.slot(method, index) if journal else None)
                for index, case in enumerate(inputs)]
    return {"summary": score(rows, gold), "attempts": rows}


class Replay:
    """Replay raw Converse responses; supplied provenance is not independent attestation."""
    def __init__(self, packet, inputs):
        self.packet = packet
        self.inputs = inputs
        self.position = 0
        self.errors = []
        expected = [case["id"] for case in inputs]
        actual = [row.get("case_id") for row in packet.get("attempts", [])]
        if actual != expected:
            self.errors.append("Missing/duplicate/extra/reordered slots; entire cohort invalid")

    def __call__(self, request, view):
        index = self.position
        self.position += 1
        if self.errors:
            raise ValueError(self.errors[0])
        row = self.packet["attempts"][index]
        if row["request_sha256"] != sha256(encoded(request)):
            raise ValueError("Replay request hash mismatch")
        if row.get("error"):
            raise RuntimeError(f"Retained adapter failure: {row['error']}")
        return row["raw_response"]


def request_plan(protocol, inputs):
    # A null-response capture obtains the exact existing adapter prompt without posting anything.
    # Plan generation does not read gold or calculate a score and never constructs a cloud client.
    rows = [observe(case, protocol,
                    lambda request, view: encoded(envelope({"kind": None})).decode())
            for case in inputs]
    return {"status": "INERT_NOT_AUTHORIZED", "protocol_sha256": PINS["protocol.json"],
            "model_configuration": protocol["model_request"],
            "attempts": [{k: r[k] for k in ("case_id", "request", "request_sha256",
                                          "raw_source_sha256", "sanitized_source_sha256")}
                         for r in rows]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("Evaluation is source CI-only; no local evaluation or live mode")
    if git("rev-parse", "HEAD") != args.candidate_sha:
        parser.error("Exact checked-out source SHA required")
    git("merge-base", "--is-ancestor", PREREGISTRATION, args.candidate_sha)
    git("diff", "--exit-code", "HEAD", "--", "src", "evaluation", "tests", ".github", "README.md")
    protocol, inputs, gold = load_frozen()
    methods = ["baseline", "always_abstain", "malformed"]
    if args.replay:
        methods.append("archived_response_replay")
    journal = Journal(args.output, inputs, methods)
    for name in (*PINS, "prior-inventory.json"):
        journal.write(name, (DATA / name).read_bytes())
    paths = git("ls-files", "src", "evaluation", "tests/test_ar3_evaluation.py",
                ".github/workflows/ci.yml", "pyproject.toml", "evidence/*.txt").splitlines()
    manifest = {name: sha256((ROOT / name).read_bytes()) for name in paths}
    journal.write("source-sha256.json", encoded(manifest))
    receipt = {"run_url": f"https://github.com/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/"
                          f"{os.getenv('GITHUB_RUN_ID')}",
               "candidate_sha": args.candidate_sha, "preregistration": PREREGISTRATION,
               "mode": "OFFLINE_SOURCE_ONLY", "live_model_invocations": 0,
               "python": platform.python_version(), "strands": version("strands-agents"),
               "boto3": version("boto3"), "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
               "model_configuration": protocol["model_request"]}
    journal.write("receipt.json", encoded(receipt))
    replay_raw = None
    if args.replay:
        replay_raw = args.replay.read_bytes()
        journal.write("replay-input.json", replay_raw)
        try:
            packet = strict_json(replay_raw.decode())
            if not isinstance(packet, dict) or not isinstance(packet.get("attempts"), list):
                raise InvalidResponse("Malformed replay cohort")
            if any(not isinstance(row, dict) for row in packet["attempts"]):
                raise InvalidResponse("Malformed replay row")
        except (InvalidResponse, UnicodeDecodeError) as exc:
            packet = {"attempts": [], "provenance": None, "parse_error": str(exc)}
        replay = Replay(packet, inputs)
    results = {"baseline": evaluate(inputs, gold, protocol, baseline, journal, "baseline")}
    controls = {"always_abstain": evaluate(inputs, gold, protocol,
                lambda request, view: encoded(envelope({"kind": None})).decode(),
                journal, "always_abstain"),
                "malformed": evaluate(inputs, gold, protocol, lambda request, view: "not JSON",
                                      journal, "malformed")}
    if args.replay:
        results["archived_response_replay"] = evaluate(inputs, gold, protocol, replay,
                                                      journal, "archived_response_replay")
        results["archived_response_replay"]["declared_provenance"] = packet.get("provenance")
        results["archived_response_replay"]["cohort_errors"] = replay.errors
    result = {"scope": protocol["scope"], "status": "SOURCE_PREPARED_NOT_REAL_MODEL_MEASURED",
              "candidate_sha": args.candidate_sha, "preregistration": PREREGISTRATION,
              "frozen_sha256": PINS, "authorship": protocol["authorship"],
              "real_model_measurement": "NOT_MEASURED; replay provenance is not authenticated",
              "model_cost_usd": None, "aws_infrastructure_cost_usd": None,
              "methods": results, "fake_controls": controls,
              "instrument_valid": (controls["always_abstain"]["summary"]["exact_captures"] == 0
                  and controls["malformed"]["summary"]["statuses"]["invalid_response"] == 12
                  and results["baseline"]["summary"]["cohort_complete"]
                  and results["baseline"]["summary"]["statuses"]["execution_error"] == 0
                  and results["baseline"]["summary"]["statuses"]["invalid_response"] == 0),
              "remaining_gates": {"AR3": "OPEN", "C1": "OPEN", "activation": "OWNER_GATED"}}
    journal.write("inert-requests.json", encoded(request_plan(protocol, inputs)))
    journal.finalize(result)
    print(json.dumps({"status": result["status"], "instrument_valid": result["instrument_valid"],
                      "baseline": results["baseline"]["summary"]}, indent=2))
    return 0 if result["instrument_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
