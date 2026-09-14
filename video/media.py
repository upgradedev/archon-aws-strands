"""CI media pipeline (Python stdlib, ffmpeg/ffprobe); no application dependencies.

python video/media.py {narrate,assemble,verify} --root OUT --spec video/story.json
Spec paths resolve from cwd; all media paths resolve from root. Capture must supply
clips/<id>.mp4 with exactly timing.json's frames, dimensions and frame rate.
Outputs: archon-demo.mp4, archon-demo.en.srt, captions.json, receipt.json.
Keep narration/ including *.attempt.json across CI runs: unresolved attempts need
human reconciliation, never automatic rebilling. The 12,000-character budget is
cumulative within this root, including failed attempts. No key is stored or logged.
Captions use ElevenLabs character alignment, or explicitly labelled scene timing.
Selectable English subtitles preserve the UI. Optional --check-frames establishes clip
continuity, not authenticity of the source capture or deployed-service provenance.
API: https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
"""

import argparse
import base64
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import textwrap
import urllib.error
import urllib.request
from fractions import Fraction
from pathlib import Path

FPS, WIDTH, HEIGHT, LEAD, CHAR_CAP = 25, 1920, 1080, 0.3, 12000
MOVIE, SRT = "archon-demo.mp4", "archon-demo.en.srt"


class MediaError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise MediaError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical(value) + b"\n")
    temporary.replace(path)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_spec(spec):
    require((spec["fps"], spec["width"], spec["height"]) == (FPS, WIDTH, HEIGHT),
            "spec must be 1920x1080 at 25fps")
    require(number(spec["targetSeconds"]) and 280 <= spec["targetSeconds"] < 299,
            "targetSeconds must be in [280,299)")
    for name in ("frontend", "backend"):
        require(re.fullmatch(r"[0-9a-f]{40}", spec[name]), "frozen SHA required: " + name)
    voice = spec["voice"]
    require(re.fullmatch(r"[A-Za-z0-9_-]+", voice["voiceId"]), "invalid voiceId")
    require(voice["modelId"] == "eleven_multilingual_v2", "unsupported model/billing contract")
    settings = voice["settings"]
    require(isinstance(settings, dict), "voice settings required")
    for name in ("stability", "similarity_boost"):
        require(number(settings.get(name)) and 0 <= settings[name] <= 1, "invalid voice " + name)
    require(type(settings.get("use_speaker_boost")) is bool, "speaker boost must be boolean")
    require(0 < len(spec["scenes"]) <= 40, "expected 1..40 scenes")
    ids = []
    for scene in spec["scenes"]:
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", scene["id"]), "unsafe scene id")
        require(scene["kind"] in ("slide", "demo"), "invalid scene kind")
        require(isinstance(scene["speech"], str) and scene["speech"].strip(), "speech required")
        require(number(scene["minSeconds"]) and 0 < scene["minSeconds"] < 299,
                "invalid scene minimum")
        ids.append(scene["id"])
    require(len(ids) == len(set(ids)), "duplicate scene id")
    canonical(spec)


def audio_path(root, scene, voice):
    key = digest([scene["speech"], voice, "mp3_44100_128", "with-timestamps-v1"])
    return root / "narration" / f"{scene['id']}-{key}.mp3"


def run(args):
    result = subprocess.run([str(a) for a in args], capture_output=True, check=False)
    require(result.returncode == 0, f"{args[0]} failed (exit {result.returncode})")
    return result.stdout


def probe(path):
    require(path.is_file(), "missing media: " + path.name)
    return json.loads(run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                           "-show_format", "-of", "json", path]))


def stream(info, kind):
    found = [s for s in info["streams"] if s["codec_type"] == kind]
    require(len(found) == 1, "expected one " + kind + " stream")
    return found[0]


def speech_seconds(path):
    info = probe(path)
    stream(info, "audio")
    seconds = float(info["format"]["duration"])
    require(math.isfinite(seconds) and 0 < seconds < 298, "invalid narration duration")
    return seconds


def make_timing(spec, durations, root):
    rows, cursor = [], 0
    for scene, speech in zip(spec["scenes"], durations, strict=True):
        require(number(speech) and speech > 0, "invalid speech duration")
        frames = math.ceil(max(scene["minSeconds"], speech + 1.0) * FPS)
        rows.append(dict(id=scene["id"], kind=scene["kind"], speechSeconds=speech,
                         seconds=frames / FPS, frames=frames, startSeconds=cursor / FPS,
                         audio=audio_path(root, scene, spec["voice"]).relative_to(root).as_posix()))
        cursor += frames
    return dict(specHash=digest(spec), totalSeconds=cursor / FPS, scenes=rows)


def target_gate(timing):
    require(280 <= timing["totalSeconds"] < 299,
            f"measured total {timing['totalSeconds']:.3f}s outside [280,299); adjust scene minima/speech")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MediaError(f"ElevenLabs HTTP {code}")


def eleven(key, endpoint, payload=None):
    request = urllib.request.Request("https://api.elevenlabs.io/v1/" + endpoint,
                                    data=canonical(payload) if payload is not None else None,
                                    headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=120) as response:
            raw = response.read(32 * 1024 * 1024 + 1)
        require(len(raw) <= 32 * 1024 * 1024, "ElevenLabs response exceeds bound")
        return json.loads(raw)
    except urllib.error.HTTPError as error:
        raise MediaError(f"ElevenLabs HTTP {error.code}") from None
    except (OSError, ValueError) as error:
        if isinstance(error, MediaError):
            raise
        raise MediaError("ElevenLabs transport/response failure; no retry") from None


def cached(path):
    sidecar = path.with_suffix(".json")
    if not path.exists() and not sidecar.exists():
        require(not path.with_suffix(".attempt.json").exists(),
                "unresolved billed attempt; reconcile manually: " + path.stem)
        return False
    require(path.is_file() and sidecar.is_file(), "incomplete narration cache; reconcile manually")
    require(read(sidecar)["audioSha256"] == sha(path), "narration cache hash mismatch")
    return True


def narrate(root, spec):
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "narration.lock"
    with lock.open("x"):
        pass
    try:
        return narrate_locked(root, spec)
    finally:
        lock.unlink()  # A killed process leaves a lock requiring manual reconciliation.


def narrate_locked(root, spec):
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    require(key, "ELEVENLABS_API_KEY is required")
    directory = root / "narration"
    directory.mkdir(parents=True, exist_ok=True)
    jobs = [(s, audio_path(root, s, spec["voice"])) for s in spec["scenes"]]
    missing = [(s, p) for s, p in jobs if not cached(p)]
    new_chars = sum(len(s["speech"]) for s, _ in missing)
    attempts = [read(p)["characters"] for p in directory.glob("*.attempt.json")]
    require(all(type(n) is int and 0 < n <= CHAR_CAP for n in attempts), "invalid attempt ledger")
    spent = sum(attempts)
    require(spent + new_chars <= CHAR_CAP, "12,000 cumulative new-character cap exceeded")
    for scene, path in missing:
        with path.with_suffix(".attempt.json").open("xb") as attempt:
            attempt.write(canonical(dict(characters=len(scene["speech"]))))
            attempt.flush()
            os.fsync(attempt.fileno())
        voice = spec["voice"]
        result = eleven(key, f"text-to-speech/{voice['voiceId']}/with-timestamps"
                        "?output_format=mp3_44100_128", dict(text=scene["speech"],
                        model_id=voice["modelId"], voice_settings=voice["settings"]))
        save(path.with_suffix(".response.json"), result)  # Retain spent data before decoding.
        audio = base64.b64decode(result["audio_base64"], validate=True)
        require(len(audio) > 0, "empty ElevenLabs audio; no retry")
        path.write_bytes(audio)
        save(path.with_suffix(".json"), dict(audioSha256=sha(path),
             alignment=result.get("alignment"), normalized_alignment=result.get("normalized_alignment")))
    timing = make_timing(spec, [speech_seconds(p) for _, p in jobs], root)
    save(root / "timing.json", timing)  # Retain measurements even when the target gate fails.
    save(root / "captions.json", make_captions(root, spec, timing))
    target_gate(timing)
    return dict(totalSeconds=timing["totalSeconds"], newCharacters=new_chars)


def make_captions(root, spec, timing):
    cues = []
    for scene, beat in zip(spec["scenes"], timing["scenes"], strict=True):
        metadata = read(root / Path(beat["audio"]).with_suffix(".json"))
        alignment = metadata.get("normalized_alignment") or metadata.get("alignment")
        offset = beat["startSeconds"] + LEAD
        if not alignment:
            cues.append(dict(id=scene["id"], start=offset, end=offset + beat["speechSeconds"],
                             text=scene["speech"], alignment="scene"))
            continue
        chars = alignment["characters"]
        starts, ends = alignment["character_start_times_seconds"], alignment["character_end_times_seconds"]
        require(len(chars) == len(starts) == len(ends) and chars, "invalid alignment lengths")
        previous = 0
        for char, start, end in zip(chars, starts, ends, strict=True):
            require(isinstance(char, str) and len(char) == 1 and number(start) and number(end)
                    and previous <= start <= end <= beat["speechSeconds"], "invalid character alignment")
            previous = end
        text = "".join(chars)
        words = list(re.finditer(r"\S+", text))
        require(words, "empty aligned caption")
        group = []
        for word in words:
            group.append(word)
            if len(group) >= 8 or word.end() - group[0].start() >= 64 or word is words[-1]:
                start, end = starts[group[0].start()], ends[word.end() - 1]
                require(end > start, "empty aligned interval")
                cues.append(dict(id=scene["id"], start=offset + start, end=offset + end,
                                 text=text[group[0].start():word.end()], alignment="elevenlabs-character"))
                group = []
    return cues


def stamp(value):
    ms = round(value * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt_text(cues):
    return "\n\n".join(f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n"
                       + textwrap.fill(" ".join(c["text"].split()), width=42)
                       for i, c in enumerate(cues, 1)) + "\n"


def check_captions(cues, timing):
    previous, seen = 0, []
    beats = {b["id"]: b for b in timing["scenes"]}
    for cue in cues:
        beat = beats[cue["id"]]
        a, b = cue["start"], cue["end"]
        require(number(a) and number(b) and previous <= a < b <= timing["totalSeconds"],
                "captions overlap or are outside duration")
        require(a >= beat["startSeconds"] + LEAD - 0.001
                and b <= beat["startSeconds"] + LEAD + beat["speechSeconds"] + 0.001,
                "caption outside narration beat")
        require(cue["text"].strip() and round(b * 1000) > round(a * 1000), "empty caption")
        previous = b
        if not seen or seen[-1] != cue["id"]:
            seen.append(cue["id"])
    require(seen == list(beats), "caption scene order/missing captions")


def load_inputs(root, spec):
    timing = read(root / "timing.json")
    durations = []
    for scene in spec["scenes"]:
        path = audio_path(root, scene, spec["voice"])
        require(cached(path), "missing narration")
        durations.append(speech_seconds(path))
    require(timing == make_timing(spec, durations, root), "timing/spec/audio contract or order mismatch")
    target_gate(timing)
    cues = read(root / "captions.json")
    check_captions(cues, timing)
    require(cues == make_captions(root, spec, timing), "captions differ from provider/scene timing")
    expected = {s["id"] + ".mp4" for s in spec["scenes"]}
    require({p.name for p in (root / "clips").glob("*.mp4")} == expected, "missing/extra clips")
    for beat in timing["scenes"]:
        video = stream(probe(root / "clips" / (beat["id"] + ".mp4")), "video")
        check_video(video, spec, beat["frames"], beat["seconds"], tolerance=0.001)
    return timing, cues


def check_video(video, spec, frames, seconds, tolerance=1 / FPS):
    require((video["width"], video["height"]) == (spec["width"], spec["height"]), "wrong dimensions")
    require(Fraction(video["avg_frame_rate"]) == FPS and Fraction(video["r_frame_rate"]) == FPS,
            "wrong frame rate")
    require(int(video["nb_read_frames"]) == frames, "wrong video frame count")
    require(abs(float(video["duration"]) - seconds) <= tolerance, "wrong video duration")
    require(abs(float(video.get("start_time", 0))) <= 0.001, "video starts away from zero")


def assemble(root, spec, check_frames=False):
    timing, cues = load_inputs(root, spec)
    (root / SRT).write_text(srt_text(cues), encoding="utf-8")
    args, filters, videos, audios = ["ffmpeg", "-nostdin", "-y", "-v", "error"], [], [], []
    beats = timing["scenes"]
    for beat in beats:
        args += ["-i", root / "clips" / (beat["id"] + ".mp4")]
    for beat in beats:
        args += ["-i", root / beat["audio"]]
    args += ["-i", root / SRT]
    for i, beat in enumerate(beats):
        filters.append(f"[{i}:v]setpts=PTS-STARTPTS,setsar=1[v{i}]")
        filters.append(f"[{i + len(beats)}:a]aresample=48000,aformat=channel_layouts=stereo,"
                       f"asetpts=PTS-STARTPTS,adelay=300:all=1,apad,"
                       f"atrim=end_sample={beat['frames'] * 1920},asetpts=N/SR/TB[a{i}]")
        videos.append(f"[v{i}]")
        audios.append(f"[a{i}]")
    filters.append("".join(videos) + f"concat=n={len(beats)}:v=1:a=0,format=yuv420p[v]")
    samples = sum(b["frames"] for b in beats) * 1920
    filters.append("".join(audios) + f"concat=n={len(beats)}:v=0:a=1,"
                   f"loudnorm=I=-16:LRA=7:TP=-1.5,aresample=48000,apad,atrim=end_sample={samples}[a]")
    run(args + ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
                "-map", f"{2 * len(beats)}:0", "-c:v", "libx264", "-preset", "medium",
                "-crf", "18", "-r", str(FPS), "-fps_mode", "cfr", "-c:a", "aac",
                "-b:a", "192k", "-ar", "48000", "-ac", "2", "-c:s", "mov_text",
                "-metadata:s:s:0", "language=eng", "-metadata:s:a:0", "language=eng",
                "-movflags", "+faststart", "-t", str(timing["totalSeconds"]), root / MOVIE])
    receipt = inspect_output(root, spec, timing, cues, check_frames=check_frames)
    save(root / "receipt.json", receipt)
    return receipt


def representative(path, seconds):
    pixels = run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{seconds:.6f}", "-i", path,
                  "-map", "0:v:0", "-frames:v", "1", "-vf", "scale=64:36", "-pix_fmt", "rgb24",
                  "-f", "rawvideo", "pipe:1"])
    require(len(pixels) == 64 * 36 * 3, "missing representative frame")
    return pixels


def faststart(path):
    with path.open("rb") as source:
        while header := source.read(8):
            require(len(header) == 8, "invalid MP4 atom")
            size, kind = struct.unpack(">I4s", header)
            header_size = 8
            if size == 1:
                size, header_size = struct.unpack(">Q", source.read(8))[0], 16
            if kind in (b"moov", b"mdat"):
                return kind == b"moov"
            require(size >= header_size, "invalid MP4 atom size")
            source.seek(size - header_size, 1)
    return False


def inspect_output(root, spec, timing, cues, check_frames=False):
    check_captions(cues, timing)
    require((root / SRT).read_text(encoding="utf-8") == srt_text(cues), "SRT differs from captions")
    movie = root / MOVIE
    info = probe(movie)
    video, audio = stream(info, "video"), stream(info, "audio")
    total = float(info["format"]["duration"])
    require(math.isfinite(total) and 0 < total < 300, "duration must be below 300 seconds")
    check_video(video, spec, sum(b["frames"] for b in timing["scenes"]), timing["totalSeconds"])
    require(abs(float(audio["duration"]) - float(video["duration"])) <= 1 / FPS
            and abs(float(audio.get("start_time", 0))) <= 1 / FPS
            and abs(float(audio.get("start_time", 0)) + float(audio["duration"])
                    - float(video["duration"])) <= 1 / FPS
            and abs(total - timing["totalSeconds"]) <= 1 / FPS, "audio/video duration mismatch")
    require(video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
            and audio["codec_name"] == "aac" and int(audio["sample_rate"]) == 48000,
            "expected H264/yuv420p and AAC 48kHz")
    subtitle = stream(info, "subtitle")
    require(subtitle["codec_name"] == "mov_text" and subtitle.get("tags", {}).get("language") == "eng",
            "missing embedded English subtitles")
    require(faststart(movie), "MP4 is not faststart")
    levels = subprocess.run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(movie), "-map", "0:a:0",
                             "-af", "volumedetect", "-f", "null", "-"], capture_output=True)
    peak = re.search(rb"max_volume: ([-\d.]+) dB", levels.stderr)
    require(levels.returncode == 0 and peak and float(peak[1]) > -60, "no audible audio")
    files = [MOVIE, SRT, "timing.json", "captions.json"]
    samples = []
    for beat in timing["scenes"]:
        clip = root / "clips" / (beat["id"] + ".mp4")
        files += [clip.relative_to(root).as_posix(), beat["audio"],
                  Path(beat["audio"]).with_suffix(".json").as_posix()]
        for frame in sorted({0, beat["frames"] // 2, beat["frames"] - 1}) if check_frames else ():
            reference = representative(clip, frame / FPS)
            encoded = representative(movie, beat["startSeconds"] + frame / FPS)
            mae = sum(abs(a - b) for a, b in zip(reference, encoded, strict=True)) / len(reference)
            require(mae <= 6, "source-frame/order mismatch: " + beat["id"])
            samples.append(dict(id=beat["id"], frame=frame, meanAbsoluteError=mae,
                                sourceSha256=hashlib.sha256(reference).hexdigest(),
                                encodedSha256=hashlib.sha256(encoded).hexdigest()))
    return dict(frontend=spec["frontend"], backend=spec["backend"], specHash=digest(spec),
                actualDuration=total, sha256=sha(movie), scenes=timing["scenes"],
                hashes={p: sha(root / p) for p in files}, frameSamples=samples,
                sourceAuthenticity="capture provenance is separate; pixel samples optional")


def verify(root, spec):
    timing, cues = load_inputs(root, spec)
    receipt = read(root / "receipt.json")
    actual = inspect_output(root, spec, timing, cues, check_frames=bool(receipt["frameSamples"]))
    require(receipt == actual, "receipt/hash/frozen SHA mismatch")
    return dict(verified=True, seconds=actual["actualDuration"], sha256=actual["sha256"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("narrate", "assemble", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--check-frames", action="store_true", help="optional assemble pixel samples")
    args = parser.parse_args()
    try:
        spec = read(args.spec)
        validate_spec(spec)
        require(not args.check_frames or args.command == "assemble", "--check-frames is for assemble")
        root = args.root.resolve()
        result = (assemble(root, spec, args.check_frames) if args.command == "assemble"
                  else globals()[args.command](root, spec))
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
        # Validation messages are authored locally; never print external response bodies or keys.
        parser.exit(1, (str(error) if isinstance(error, MediaError) else "invalid media input") + "\n")


if __name__ == "__main__":
    main()
