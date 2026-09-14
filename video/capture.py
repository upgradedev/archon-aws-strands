"""Capture the frozen public application once, without mocks or hidden mutations.

Run on CI only. CDP frames and action times preserve the actual rendered screen.
An incomplete take is deliberately not retried: inspect provider state first.
The exported manifest contains no workspace bearer handle or request payload.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import time

from playwright.sync_api import sync_playwright, expect


def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


class Director:
    def __init__(self, page, root, timing):
        self.page, self.root, self.timing = page, root, timing
        self.frames, self.events, self.scenes = [], [], []
        self.pointer = (60, 60)
        self.cuts = []
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self.frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90,
                      "maxWidth": 1600, "maxHeight": 900, "everyNthFrame": 1})

    def frame(self, event):
        # CDP uses Unix-epoch seconds, as do the action events. Callback arrival
        # can lag the captured pixels while synchronous browser work is busy.
        now = float(event["metadata"]["timestamp"])
        name = f"frames/{len(self.frames):06d}.jpg"
        (self.root / name).write_bytes(base64.b64decode(event["data"]))
        self.frames.append({"t": now, "path": name})
        self.cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})

    def pause(self, seconds):
        self.page.wait_for_timeout(max(1, int(seconds * 1000)))

    def scroll(self, locator):
        locator.wait_for(state="visible")
        locator.evaluate("e => e.scrollIntoView({behavior:'smooth',block:'center'})")
        self.pause(1.1)

    def move(self, locator):
        self.scroll(locator)
        box = locator.bounding_box()
        target = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        start = time.time()
        self.page.mouse.move(*target, steps=24)
        self.events.append({"kind": "move", "t0": start, "t1": time.time(),
                            "from": self.pointer, "to": target})
        self.pointer = target
        self.pause(.6)

    def click(self, locator):
        self.move(locator)
        self.events.append({"kind": "click", "t": time.time(), "at": self.pointer})
        locator.click()
        self.pause(.5)

    def shot(self, name):
        self.page.screenshot(path=str(self.root.parent / "screenshots" / f"{name}.png"))

    def begin(self, name):
        self.current = {"id": name, "start": time.time(), "cuts": []}
        print("Recording", name, flush=True)

    def end(self):
        target = self.timing[self.current["id"]]["seconds"]
        trimmed = sum(b - a for a, b in self.current["cuts"])
        elapsed = time.time() - self.current["start"] - trimmed
        if elapsed > target + .04:
            raise ValueError(f"Scene {self.current['id']} exceeds narration window: {elapsed:.2f}/{target}")
        self.pause(target - elapsed + .12)
        self.current["end"] = time.time()
        self.scenes.append(self.current)

    def wait_job(self):
        start = time.time()
        expect(self.page.locator("main")).to_have_attribute("aria-busy", "false", timeout=120000)
        result = saved(self.page)
        assert result["live"]["job"]["status"] == "completed", "Provider job did not complete"
        end = time.time()
        if end - start > 3.5:
            self.current["cuts"].append([start + 1.5, end - .8])
        return result


def saved(page):
    handle = page.evaluate("localStorage.getItem('archon.demo.session.v1')")
    assert handle and len(handle) == 64
    result = page.request.get("/api/workspace", headers={"X-Archon-Session": handle})
    assert result.status == 200
    return result.json()


def journey(d, page, recipient):
    tid = page.get_by_test_id
    role = page.get_by_role
    d.begin("entry")
    d.shot("01-welcome")
    d.pause(5)
    d.click(role("link", name="Explore populated demo", exact=True))
    d.click(role("button", name="Load business portfolio", exact=True))
    expect(role("region", name="Current demo dataset")).to_contain_text("240 source records")
    d.end()

    d.begin("dashboard")
    state = saved(page)
    assert len(state["sources"]) == 240 and not state["graph"] and not state["receipts"]
    d.scroll(tid("business-net-sales")); d.pause(4); d.shot("02-financial-dashboard")
    d.scroll(role("table", name="Monthly cash records", exact=False)); d.pause(4)
    d.shot("03-cash-and-aging")
    d.scroll(role("table", name="Top clients", exact=True)); d.pause(3)
    d.shot("04-counterparties")
    d.end()

    d.begin("records")
    page.goto("/#/records?view=sales-invoices")
    expect(role("table", name="Sales invoices", exact=True)).to_be_visible()
    d.scroll(role("table", name="Sales invoices", exact=True)); d.pause(4); d.shot("05-sales-invoices")
    page.goto("/#/records?view=sales-credits")
    expect(role("table", name="Sales credits", exact=True)).to_be_visible()
    d.scroll(role("table", name="Sales credits", exact=True)); d.pause(4); d.shot("06-credit-notes")
    page.goto("/#/records?view=supplier-payments")
    expect(role("table", name="Supplier payments", exact=True)).to_be_visible()
    d.scroll(role("table", name="Supplier payments", exact=True)); d.pause(3)
    d.end()

    d.begin("case")
    page.goto("/#/demo")
    d.click(role("button", name="Load demo workspace", exact=True))
    expect(role("region", name="Populated fictional demo")).to_be_visible()
    page.goto("/#/workspace")
    arithmetic = page.locator('[aria-label="Invoice arithmetic"]')
    expect(arithmetic).to_contain_text("1,260.00 EUR")
    d.scroll(arithmetic); d.pause(4); d.shot("07-source-and-balance")
    d.click(page.locator('.source-choice').filter(has_text="Recorded receipt").first)
    d.pause(4); d.shot("08-payment-evidence")
    d.end()

    d.begin("run")
    write(d.root / "provider-started.json", {"started": time.time(), "operation": "reason"})
    d.click(role("button", name="Run Strands & prepare draft", exact=True))
    draft_state = d.wait_job()
    assert draft_state["draft"] and not draft_state["receipts"]
    calls = draft_state["live"]["job"]["calls"]
    assert len(calls) >= 7 and all(c["usage"]["inputTokens"] > 0 for c in calls)
    d.scroll(tid("provider-status"))
    summary = tid("provider-status").locator("summary")
    d.click(summary); d.pause(3); d.shot("09-real-bedrock-execution")
    d.end()

    d.begin("draft")
    d.scroll(page.locator("#collection-draft")); d.pause(6); d.shot("10-generated-email")
    d.click(page.get_by_text("Linked ledger evidence", exact=True))
    d.pause(4); d.shot("11-linked-evidence")
    d.click(page.get_by_text("Linked ledger evidence", exact=True))
    d.click(page.get_by_text("Six domain reports · inspect", exact=True)); d.pause(3)
    d.end()

    d.begin("review")
    d.scroll(page.locator("#collection-draft"))
    d.click(page.get_by_text("Exact content fingerprint", exact=True)); d.pause(3)
    send = role("button", name="Approve exact draft · send real email", exact=True)
    expect(send).to_be_disabled()
    d.move(send); d.pause(4); d.shot("12-human-approval")
    d.end()

    d.begin("send")
    checked = saved(page)
    draft = checked["draft"]
    assert checked["live"]["mail"] and draft["recipient"] == recipient
    assert checked["sales"][0]["outstanding"] == "1260.00"
    assert draft["subject"].startswith("[Archon controlled test]")
    assert "1260" in draft["body"].replace(",", "").replace(" ", "")
    assert draft["fingerprint"] == draft_state["draft"]["fingerprint"]
    consent = role("checkbox", name="I reviewed this recipient, subject, body and balance. I authorize this real email to the verified test recipient.")
    d.click(consent); expect(send).to_be_enabled(); d.pause(2)
    d.click(send)
    final = d.wait_job()
    assert len(final["receipts"]) == 1
    receipt = final["receipts"][0]
    assert receipt["state"] == "provider-accepted" and receipt["message_id"]
    assert not receipt["message_id"].startswith(("ci-", "simulated-"))
    d.scroll(role("heading", name="Delivery receipts", exact=False)); d.pause(3)
    d.shot("13-real-ses-receipt")
    d.end()

    d.begin("receipt")
    page.reload()
    expect(role("heading", name="History", exact=True)).to_be_visible()
    after = saved(page)
    assert after["receipts"] == final["receipts"] and after["live"]["history"] == final["live"]["history"]
    d.scroll(role("heading", name="Delivery receipts", exact=False)); d.pause(5)
    d.click(page.get_by_text("Approved content fingerprint", exact=True)); d.pause(3)
    d.shot("14-durable-approval")
    d.end()

    d.begin("tour")
    d.click(role("button", name="Take a tour", exact=True))
    d.scroll(role("region", name="Product tour", exact=True)); d.pause(3)
    d.click(role("button", name="Next stop", exact=True)); d.pause(3)
    d.shot("15-product-tour")
    d.end()
    return {"scope": "actual_aws", "model_calls": len(calls), "email_accepted": True,
            "delivery_proven": False, "receipt_id": receipt["message_id"],
            "fingerprint": receipt["fingerprint"], "reload_retained": True,
            "invoice_total": "1860.00", "recorded_payment": "600.00", "outstanding": "1260.00"}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--spec", type=Path, default=Path("video/story.json")); args = parser.parse_args()
    spec = json.loads(args.spec.read_text()); root = args.root / "capture"
    root.mkdir(parents=True, exist_ok=True); (root / "frames").mkdir(exist_ok=True)
    (args.root / "screenshots").mkdir(exist_ok=True)
    complete, attempt = root / "manifest.json", root / "attempt.json"
    if complete.exists():
        saved_manifest = json.loads(complete.read_text())
        assert saved_manifest["frontend"] == spec["frontend"] and saved_manifest["backend"] == spec["backend"]
        print("Reusing completed capture; no provider operation."); return
    assert not (root / "provider-started.json").exists(), "Prior provider take incomplete. Reconcile live state; do not replay."
    assert os.environ.get("CI") == "true" and os.environ.get("ARCHON_VIDEO_LIVE_CAPTURE") == "approved"
    recipient = os.environ["ARCHON_VIDEO_RECIPIENT"]
    timing = {s["id"]: s for s in json.loads((args.root / "timing.json").read_text())["scenes"]}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(base_url=spec["origin"], viewport={"width": 1600, "height": 900},
                                      device_scale_factor=1, locale="en-GB", timezone_id="Europe/Athens")
        page = context.new_page(); page.set_default_timeout(30000)
        assert page.request.get("/").status == 200
        release = page.request.get("/release.json").json()
        health = page.request.get("/api/health").json()
        assert spec["frontend"] in json.dumps(release) and health["commit"] == spec["backend"]
        assert health["mode"] == "controlled-live" and health["live_model"] and health["live_send"]
        write(attempt, {"started": time.time(), "frontend": spec["frontend"], "backend": spec["backend"]})
        page.goto("/#/welcome", wait_until="networkidle")
        expect(page.locator("#welcome-title")).to_be_visible()
        d = Director(page, root, timing); d.pause(.5)
        try:
            proof = journey(d, page, recipient)
            d.cdp.send("Page.stopScreencast")
            write(complete, {"frontend": spec["frontend"], "backend": spec["backend"],
                             "viewport": [1600, 900], "frames": d.frames, "events": d.events,
                             "scenes": d.scenes, "proof": proof})
        finally:
            write(root / "partial-index.json", {"frames": d.frames, "events": d.events, "scenes": d.scenes})
            page.screenshot(path=str(args.root / "screenshots" / "capture-last-state.png"))
            browser.close()


if __name__ == "__main__":
    main()
