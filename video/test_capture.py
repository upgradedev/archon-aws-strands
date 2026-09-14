import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from capture import Director


class CaptureClockTests(unittest.TestCase):
    def test_delayed_callback_retains_pixel_capture_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            director = Director.__new__(Director)
            director.root = Path(folder)
            (director.root / "frames").mkdir()
            director.frames, director.cdp = [], Mock()
            event = {"metadata": {"timestamp": 100.25}, "sessionId": 7,
                     "data": base64.b64encode(b"captured frame").decode()}
            with patch("capture.time.time", return_value=104.5):
                director.frame(event)
            self.assertEqual(director.frames[0]["t"], 100.25)
            self.assertEqual((director.root / director.frames[0]["path"]).read_bytes(), b"captured frame")
            director.cdp.send.assert_called_once_with("Page.screencastFrameAck", {"sessionId": 7})

    def test_pointer_motion_ends_before_hover_hold(self):
        director = Director.__new__(Director)
        director.events, director.pointer = [], (60, 60)
        director.page, director.scroll = Mock(), Mock()
        locator = Mock()
        locator.bounding_box.return_value = {"x": 90, "y": 190, "width": 20, "height": 20}
        observed = []
        director.pause = lambda seconds: observed.append((seconds, list(director.events)))
        with patch("capture.time.time", side_effect=[10, 10.4]):
            director.move(locator)
        self.assertEqual(observed[0][1][0]["t1"], 10.4)
        self.assertEqual(director.pointer, (100, 200))


if __name__ == "__main__":
    unittest.main()
