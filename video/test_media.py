"""CI only: python -m unittest discover -s video -p test_media.py -v.

No network or real speech generation. FFmpeg controls use two tiny color clips and
a tone. inspect_output checks media independent of the production 280-second floor;
load_inputs enforces that floor and has separate boundary tests below.
"""

import base64
import copy
import io
import os
import struct
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

try:
    from video import media
except ModuleNotFoundError:
    import media


def story():
    return dict(fps=25, width=1920, height=1080, targetSeconds=290,
                frontend="a" * 40, backend="b" * 40,
                voice=dict(voiceId="pNInz6obpgDQGcFmaJgB", modelId="eleven_multilingual_v2",
                           settings=dict(stability=0.5, similarity_boost=0.8,
                                         use_speaker_boost=True)),
                scenes=[dict(id="intro", kind="slide", speech="Hello world.", minSeconds=145),
                        dict(id="demo", kind="demo", speech="A real demo.", minSeconds=145)])


def cache(root, spec):
    (root / "narration").mkdir(exist_ok=True)
    for scene in spec["scenes"]:
        path = media.audio_path(root, scene, spec["voice"])
        path.write_bytes(b"offline unit-test audio placeholder")
        media.save(path.with_suffix(".json"), dict(audioSha256=media.sha(path), alignment=None))


class PureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.spec = story()

    def test_exact_text_voice_cache(self):
        scene, voice = self.spec["scenes"][0], self.spec["voice"]
        path = media.audio_path(self.root, scene, voice)
        self.assertEqual(path, media.audio_path(self.root, scene, dict(reversed(list(voice.items())))))
        for changed in (dict(scene, speech="Hello world. "), dict(scene, speech="hello world.")):
            self.assertNotEqual(path, media.audio_path(self.root, changed, voice))
        changed_voice = copy.deepcopy(voice)
        changed_voice["settings"]["stability"] = 0.51
        self.assertNotEqual(path, media.audio_path(self.root, scene, changed_voice))
        self.assertEqual(path, media.audio_path(self.root, dict(scene, minSeconds=150), voice))

    def test_measured_per_beat_rounding_and_relative_paths(self):
        self.spec["scenes"][0]["minSeconds"] = 1
        timing = media.make_timing(self.spec, [2.001, 3], self.root)
        first, second = timing["scenes"]
        self.assertEqual((first["frames"], first["seconds"]), (76, 3.04))
        self.assertEqual((second["startSeconds"], second["frames"]), (3.04, 3625))
        self.assertEqual(timing["totalSeconds"], 148.04)
        self.assertTrue(first["audio"].startswith("narration/intro-"))
        self.assertFalse(Path(first["audio"]).is_absolute())

    def test_target_boundaries_are_fixed(self):
        for value in (280, 290, 298.96):
            media.target_gate(dict(totalSeconds=value))
        for value in (279.96, 299, 300, float("nan")):
            with self.assertRaises(media.MediaError):
                media.target_gate(dict(totalSeconds=value))

    def test_spec_contract_negative_controls(self):
        media.validate_spec(self.spec)
        for name, value in (("fps", 30), ("width", 1280), ("frontend", "unknown")):
            with self.subTest(name=name), self.assertRaises(media.MediaError):
                media.validate_spec(dict(self.spec, **{name: value}))
        for field, value in (("id", "../outside"), ("kind", "phantom"),
                             ("minSeconds", float("nan")), ("speech", "")):
            spec = copy.deepcopy(self.spec)
            spec["scenes"][0][field] = value
            with self.subTest(field=field), self.assertRaises(media.MediaError):
                media.validate_spec(spec)
        self.spec["scenes"][1]["id"] = "intro"
        with self.assertRaisesRegex(media.MediaError, "duplicate"):
            media.validate_spec(self.spec)

    def test_cache_corruption_and_uncertain_attempt_fail_closed(self):
        cache(self.root, self.spec)
        path = media.audio_path(self.root, self.spec["scenes"][0], self.spec["voice"])
        self.assertTrue(media.cached(path))
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(media.MediaError, "hash mismatch"):
            media.cached(path)
        other = self.root / "narration" / "uncertain.mp3"
        media.save(other.with_suffix(".attempt.json"), dict(characters=100))
        with self.assertRaisesRegex(media.MediaError, "unresolved billed"):
            media.cached(other)

    def test_key_precedes_network_and_http_errors_are_redacted(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(media, "eleven") as api:
            with self.assertRaisesRegex(media.MediaError, "ELEVENLABS_API_KEY"):
                media.narrate(self.root, self.spec)
            api.assert_not_called()
        with patch.object(media.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = urllib.error.HTTPError(
                "https://redacted.invalid", 401, "sensitive detail", {}, io.BytesIO(b"secret"))
            with self.assertRaises(media.MediaError) as error:
                media.eleven("secret", "text-to-speech/voice/with-timestamps", {"text": "Hello"})
            self.assertEqual(str(error.exception), "ElevenLabs HTTP 401")
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_no_automatic_billed_retry_even_on_next_invocation(self):
        responses = [media.MediaError("HTTP 503")]
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "offline"}), \
                patch.object(media, "eleven", side_effect=responses) as api:
            with self.assertRaisesRegex(media.MediaError, "503"):
                media.narrate(self.root, self.spec)
            self.assertEqual(api.call_count, 1)
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "offline"}), \
                patch.object(media, "eleven") as api:
            with self.assertRaisesRegex(media.MediaError, "unresolved billed"):
                media.narrate(self.root, self.spec)
            api.assert_not_called()

    def test_cumulative_character_cap_precedes_any_request(self):
        (self.root / "narration").mkdir()
        media.save(self.root / "narration" / "old.attempt.json", dict(characters=11999))
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "offline"}), \
                patch.object(media, "eleven") as api:
            with self.assertRaisesRegex(media.MediaError, "12,000"):
                media.narrate(self.root, self.spec)
            api.assert_not_called()

    def test_narration_cache_resume_and_retained_out_of_target_timing(self):
        result = dict(audio_base64=base64.b64encode(b"offline audio").decode(), alignment=None)
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "offline"}), \
                patch.object(media, "eleven", side_effect=[result, result]) as api, \
                patch.object(media, "speech_seconds", return_value=2):
            self.assertEqual(media.narrate(self.root, self.spec)["newCharacters"], 24)
            self.assertEqual(api.call_count, 2)
            self.assertTrue(all(call.args[1].startswith("text-to-speech/") for call in api.call_args_list))
        self.spec["scenes"][0]["minSeconds"] = 160
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "offline"}), \
                patch.object(media, "eleven") as api, \
                patch.object(media, "speech_seconds", return_value=2):
            with self.assertRaisesRegex(media.MediaError, "adjust scene"):
                media.narrate(self.root, self.spec)
            api.assert_not_called()
            self.assertEqual(media.read(self.root / "timing.json")["totalSeconds"], 305)

    def test_real_character_alignment_and_scene_fallback(self):
        cache(self.root, self.spec)
        path = media.audio_path(self.root, self.spec["scenes"][0], self.spec["voice"])
        media.save(path.with_suffix(".json"), dict(alignment=dict(characters=list("Hi all"),
                   character_start_times_seconds=[0, 0.1, 0.2, 0.7, 0.8, 0.9],
                   character_end_times_seconds=[0.1, 0.2, 0.3, 0.8, 0.9, 1.1])))
        timing = media.make_timing(self.spec, [2, 2], self.root)
        cues = media.make_captions(self.root, self.spec, timing)
        self.assertEqual(cues[0]["text"], "Hi all")
        self.assertEqual(cues[0]["alignment"], "elevenlabs-character")
        self.assertAlmostEqual(cues[0]["start"], 0.3)
        self.assertAlmostEqual(cues[0]["end"], 1.4)
        self.assertEqual(cues[1]["alignment"], "scene")
        media.check_captions(cues, timing)
        self.assertIn("00:00:00,300 --> 00:00:01,400", media.srt_text(cues))

    def test_missing_clips_order_and_stale_contract(self):
        cache(self.root, self.spec)
        timing = media.make_timing(self.spec, [2, 2], self.root)
        media.save(self.root / "timing.json", timing)
        media.save(self.root / "captions.json", media.make_captions(self.root, self.spec, timing))
        with patch.object(media, "speech_seconds", return_value=2):
            with self.assertRaisesRegex(media.MediaError, "missing/extra clips"):
                media.load_inputs(self.root, self.spec)
            timing["scenes"].reverse()
            media.save(self.root / "timing.json", timing)
            with self.assertRaisesRegex(media.MediaError, "contract or order"):
                media.load_inputs(self.root, self.spec)


@unittest.skipUnless(os.environ.get("CI", "").lower() in ("true", "1"), "FFmpeg controls run in CI only")
class FFmpegControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.spec = story()
        self.spec.update(width=160, height=90)
        for scene in self.spec["scenes"]:
            scene["minSeconds"] = 1.4
        cache(self.root, self.spec)
        self.timing = media.make_timing(self.spec, [0.25, 0.25], self.root)
        self.cues = media.make_captions(self.root, self.spec, self.timing)
        media.save(self.root / "timing.json", self.timing)
        media.save(self.root / "captions.json", self.cues)
        (self.root / media.SRT).write_text(media.srt_text(self.cues), encoding="utf-8")
        (self.root / "clips").mkdir()
        for scene, color in zip(self.spec["scenes"], ("red", "blue"), strict=True):
            media.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                       f"color=c={color}:s=160x90:r=25:d=1.4", "-an", "-c:v", "libx264",
                       "-pix_fmt", "yuv420p", self.root / "clips" / (scene["id"] + ".mp4")])

    def render(self, audio=True, audio_seconds=2.8, reverse=False):
        names = ["intro", "demo"] if not reverse else ["demo", "intro"]
        args = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
        for name in names:
            args += ["-i", self.root / "clips" / (name + ".mp4")]
        args += ["-i", self.root / media.SRT]
        if audio:
            args += ["-f", "lavfi", "-i", f"sine=frequency=880:sample_rate=48000:duration={audio_seconds}"]
        args += ["-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "2:0"]
        if audio:
            args += ["-map", "3:a", "-c:a", "aac", "-ar", "48000"]
        media.run(args + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "25", "-c:s", "mov_text",
                          "-metadata:s:s:0", "language=eng", "-movflags", "+faststart", self.root / media.MOVIE])

    def inspect(self):
        return media.inspect_output(self.root, self.spec, self.timing, self.cues, check_frames=True)

    def test_real_assembler_lead_and_per_beat_tail(self):
        for scene in self.spec["scenes"]:
            path = media.audio_path(self.root, scene, self.spec["voice"])
            media.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                       "sine=frequency=880:sample_rate=44100:duration=0.25", "-c:a", "libmp3lame", path])
            media.save(path.with_suffix(".json"), dict(audioSha256=media.sha(path), alignment=None))
        # Only input loading is replaced for a 2.8-second fixture; encoding and output gates are real.
        with patch.object(media, "load_inputs", return_value=(self.timing, self.cues)):
            result = media.assemble(self.root, self.spec)
        self.assertAlmostEqual(result["actualDuration"], 2.8, places=2)
        for start, audible in ((0.05, False), (0.35, True), (1.5, False), (1.75, True)):
            raw = media.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(start), "-i",
                             self.root / media.MOVIE, "-map", "0:a:0", "-t", "0.1", "-ac", "1",
                             "-ar", "48000", "-f", "f32le", "pipe:1"])
            values = struct.unpack("<" + "f" * (len(raw) // 4), raw)
            rms = (sum(v * v for v in values) / len(values)) ** 0.5
            if audible:
                self.assertGreater(rms, 0.01)
            else:
                self.assertLess(rms, 0.003)

    def test_valid_video_then_receipt_hash_and_source_order_controls(self):
        self.render()
        receipt = self.inspect()
        self.assertAlmostEqual(receipt["actualDuration"], 2.8, places=2)
        self.assertEqual(len(receipt["frameSamples"]), 6)
        media.save(self.root / "receipt.json", receipt)
        with patch.object(media, "load_inputs", return_value=(self.timing, self.cues)):
            self.assertTrue(media.verify(self.root, self.spec)["verified"])
            receipt["backend"] = "c" * 40
            media.save(self.root / "receipt.json", receipt)
            with self.assertRaisesRegex(media.MediaError, "receipt/hash"):
                media.verify(self.root, self.spec)
        self.render(reverse=True)
        with self.assertRaisesRegex(media.MediaError, "source-frame/order"):
            self.inspect()

    def test_audio_duration_mismatch(self):
        self.render(audio_seconds=1)
        with self.assertRaisesRegex(media.MediaError, "audio/video duration"):
            self.inspect()

    def test_missing_audio(self):
        self.render(audio=False)
        with self.assertRaisesRegex(media.MediaError, "one audio stream"):
            self.inspect()

    def test_captions_outside_and_overlap(self):
        self.render()
        self.cues[-1]["end"] = 4
        with self.assertRaisesRegex(media.MediaError, "outside duration"):
            self.inspect()
        self.cues = media.make_captions(self.root, self.spec, self.timing)
        self.cues[1]["start"] = 0.4
        with self.assertRaisesRegex(media.MediaError, "overlap"):
            self.inspect()

    def test_wrong_dimensions(self):
        self.render()
        self.spec["width"] = 1920
        with self.assertRaisesRegex(media.MediaError, "wrong dimensions"):
            self.inspect()


if __name__ == "__main__":
    unittest.main()
