from pathlib import Path
import tempfile
import unittest

from studyflow.repository import TaskRepository


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = TaskRepository(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_and_update_task(self):
        created = self.repo.create_task(
            {
                "title": "Viết slide",
                "due_at": "2026-07-31T10:00:00+00:00",
                "importance": "high",
            }
        )
        self.assertEqual(created["title"], "Viết slide")
        updated = self.repo.update_task(created["id"], {"status": "done"})
        self.assertEqual(updated["status"], "done")
        self.assertEqual(updated["progress"], 100)

    def test_checkin_records_blocker_start(self):
        created = self.repo.create_task({"title": "Chạy eval"})
        updated = self.repo.check_in(
            created["id"],
            {
                "progress": 25,
                "status": "blocked",
                "blocked_reason": "Thiếu case khó",
                "note": "Cần cả team review",
            },
        )
        self.assertEqual(updated["status"], "blocked")
        self.assertEqual(updated["blocked_reason"], "Thiếu case khó")
        self.assertIsNotNone(updated["blocked_since"])

    def test_rejects_invalid_progress(self):
        with self.assertRaises(ValueError):
            self.repo.create_task({"title": "Sai", "progress": 101})


if __name__ == "__main__":
    unittest.main()
