import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("update_trailers", Path(__file__).with_name("update_trailers.py"))
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class TrailerIndexTests(unittest.TestCase):
    def test_youtube_ids_and_rejected_hosts(self):
        self.assertEqual(updater.youtube_id("https://youtu.be/abcdefghijk"), "abcdefghijk")
        self.assertEqual(updater.youtube_id("https://www.youtube.com/watch?v=abcdefghijk"), "abcdefghijk")
        self.assertEqual(updater.youtube_id("https://youtube.com.evil.test/watch?v=abcdefghijk"), "")

    def test_index_is_bounded_and_contains_no_private_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            responses = {
                "get_vod_streams": [
                    {"stream_id": 5, "name": "Private title", "added": "200"},
                    {"stream_id": 4, "name": "Other title", "added": "100"},
                ],
                "get_series": [{"series_id": 7, "name": "Series title", "added": "100"}],
                "get_vod_info": {"info": {"youtube_trailer": "abcdefghijk"}},
                "get_series_info": {"info": {"youtube_trailer": "lmnopqrstuv"}},
            }

            def fake_request(url, headers=None):
                action = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(
                    __import__("urllib.parse", fromlist=["urlparse"]).urlparse(url).query
                )["action"][0]
                return responses[action]

            with patch.object(updater, "OUTPUT", root / "docs" / "trailers.json"), \
                 patch.object(updater, "SCRIPT_OUTPUT", root / "docs" / "trailers.js"), \
                 patch.object(updater, "STATE", root / "state" / "trailer-state.json"), \
                 patch.object(updater, "request_json", side_effect=fake_request):
                updater.update("https://private.example", "secret-user", "secret-password", batch_size=2)
                updater.update("https://private.example", "secret-user", "secret-password", batch_size=2)
                payload = (root / "docs" / "trailers.json").read_text(encoding="utf-8")
                data = json.loads(payload)
                self.assertEqual(data["movies"]["5"]["youtube"], "abcdefghijk")
                self.assertEqual(data["series"]["7"]["youtube"], "lmnopqrstuv")
                self.assertNotIn("Private title", payload)
                self.assertNotIn("secret-user", payload)
                self.assertNotIn("secret-password", payload)
                self.assertNotIn("private.example", payload)
                self.assertTrue((root / "docs" / "trailers.js").read_text().startswith("window.POBLETE_TRAILER_FEED="))


if __name__ == "__main__":
    unittest.main()
