"""Render per-beat motion slides and real CDP capture frames on the CI runner.

Only explicit idle-wait intervals are shortened. Source pixels are not replaced.
Unaltered product screenshots remain separate from the composed video frames.
"""
import argparse
import bisect
import io
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright


def raw_time(scene, offset):
    current = scene["start"] + offset
    for start, end in scene["cuts"]:
        if current >= start:
            current += end - start
    return min(current, scene["end"])


def cursor(events, t):
    position = (60, 60)
    for event in events:
        if event["kind"] != "move":
            continue
        if t < event["t0"]:
            break
        weight = min(1, (t - event["t0"]) / max(.001, event["t1"] - event["t0"]))
        weight = weight * weight * (3 - 2 * weight)
        position = tuple(a + (b - a) * weight for a, b in zip(event["from"], event["to"]))
    return position


def encoder(path):
    return subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
          "-f", "image2pipe", "-vcodec", "mjpeg", "-r", "25", "-i", "pipe:0",
          "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-threads", "2",
          "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)


def image_bytes(image):
    memory = io.BytesIO(); image.save(memory, format="JPEG", quality=94); return memory.getvalue()


def render_slides(root, spec, timing):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page.goto(Path("video/slides.html").resolve().as_uri())
        for scene in spec["scenes"]:
            if scene["kind"] != "slide": continue
            beat = timing[scene["id"]]; path = root / "clips" / f"{scene['id']}.mp4"
            page.evaluate("id=>window.show(id)", scene["id"])
            process = encoder(path)
            try:
                for frame in range(beat["frames"]):
                    page.evaluate("ms=>window.seek(ms)", frame * 40)
                    process.stdin.write(page.screenshot(type="jpeg", quality=94))
                    if frame == min(beat["frames"] - 1, 125):
                        page.screenshot(path=str(root / "review" / f"slide-{scene['id']}.png"))
            finally:
                process.stdin.close()
                assert process.wait() == 0, "Slide encode failed"
            print("Rendered", scene["id"], flush=True)
        browser.close()


def render_demo(root, spec, timing):
    capture = root / "capture"
    manifest = json.loads((capture / "manifest.json").read_text())
    assert manifest["frontend"] == spec["frontend"] and manifest["backend"] == spec["backend"]
    frames = manifest["frames"]; times = [frame["t"] for frame in frames]
    assert frames and times == sorted(times), "Capture frame timeline is invalid"
    scenes = {s["id"]: s for s in manifest["scenes"]}
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 25)
    for scene in spec["scenes"]:
        if scene["kind"] != "demo": continue
        beat, captured = timing[scene["id"]], scenes[scene["id"]]
        assert times[0] <= captured["start"]
        duration = captured["end"] - captured["start"] - sum(b-a for a,b in captured["cuts"])
        assert duration >= beat["seconds"] - .04, "Real capture is shorter than the narration"
        process = encoder(root / "clips" / f"{scene['id']}.mp4")
        previous, base = -1, None
        try:
            for i in range(beat["frames"]):
                t = raw_time(captured, i / 25)
                index = max(0, bisect.bisect_right(times, t) - 1)
                if index != previous:
                    with Image.open(capture / frames[index]["path"]) as source:
                        base = source.convert("RGB").resize((1920,1080), Image.Resampling.LANCZOS)
                    previous = index
                image = base.copy(); draw = ImageDraw.Draw(image)
                x,y = cursor(manifest["events"], t); x*=1.2; y*=1.2
                draw.polygon([(x,y),(x+5,y+28),(x+12,y+20),(x+23,y+20)],fill="#9ef4d7",outline="#05131f",width=2)
                for event in manifest["events"]:
                    if event["kind"] == "click" and 0 <= t-event["t"] < .45:
                        cx,cy=(v*1.2 for v in event["at"]); radius=12+35*(t-event["t"])
                        draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),outline="#9ef4d7",width=3)
                if captured["cuts"]:
                    draw.rounded_rectangle((32,1015,570,1065),radius=14,fill="#071423")
                    draw.text((50,1027),"Actual run · processing wait shortened",font=font,fill="#b9eedc")
                process.stdin.write(image_bytes(image))
                if i == beat["frames"] // 2:
                    image.save(root / "review" / f"demo-{scene['id']}.png")
        finally:
            process.stdin.close(); assert process.wait() == 0, "Demo encode failed"
        print("Rendered", scene["id"], flush=True)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--spec",type=Path,default=Path("video/story.json"))
    parser.add_argument("--only",choices=["posters","slides","demo","all"],default="all"); args=parser.parse_args()
    spec=json.loads(args.spec.read_text())
    (args.root/"clips").mkdir(parents=True,exist_ok=True); (args.root/"review").mkdir(exist_ok=True)
    if args.only == "posters":
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={"width":1920,"height":1080})
            page.goto(Path("video/slides.html").resolve().as_uri())
            for scene in spec["scenes"]:
                if scene["kind"] != "slide":continue
                page.evaluate("id=>window.show(id)",scene["id"])
                page.evaluate("window.seek(6000)")
                page.screenshot(path=str(args.root/"review"/f"slide-{scene['id']}.png"))
            browser.close()
        return
    timing={s["id"]:s for s in json.loads((args.root/"timing.json").read_text())["scenes"]}
    if args.only in ("slides","all"):render_slides(args.root,spec,timing)
    if args.only in ("demo","all"):render_demo(args.root,spec,timing)


if __name__=="__main__":main()
