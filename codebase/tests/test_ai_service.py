from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from studyflow.ai_service import AIService


class AIServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = AIService(
            api_key="",
            model="test-model",
            timeout_seconds=1,
            trace_path=Path(self.temp_dir.name) / "trace.jsonl",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fallback_is_explicitly_labelled(self):
        result = self.service.parse_task(
            "Làm slide gấp trước ngày mai",
            datetime(2026, 7, 30, 3, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(result["mode"], "fallback")
        self.assertIn("Chưa có GEMINI_API_KEY", result["warning"])
        self.assertEqual(result["task"]["importance"], "high")

    def test_extracts_interactions_api_text(self):
        raw = {
            "steps": [
                {
                    "type": "model_output",
                    "content": [{"type": "text", "text": '{"title":"A"}'}],
                }
            ]
        }
        self.assertEqual(self.service._extract_output_text(raw), '{"title":"A"}')

    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            self.service.parse_task("   ")


if __name__ == "__main__":
    unittest.main()
