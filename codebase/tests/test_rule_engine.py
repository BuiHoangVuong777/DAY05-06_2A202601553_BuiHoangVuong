from datetime import datetime, timedelta, timezone
import unittest

from studyflow.rule_engine import build_dashboard, enrich_and_rank, priority_for


NOW = datetime(2026, 7, 30, 3, 0, tzinfo=timezone.utc)


def task(**overrides):
    base = {
        "id": 1,
        "title": "Task mẫu",
        "assignee": "An",
        "due_at": (NOW + timedelta(days=5)).isoformat(),
        "importance": "medium",
        "status": "todo",
        "progress": 0,
        "blocked_since": None,
    }
    base.update(overrides)
    return base


class PriorityRuleTests(unittest.TestCase):
    def test_overdue_task_is_critical(self):
        result = priority_for(task(due_at=(NOW - timedelta(days=1)).isoformat()), NOW)
        self.assertEqual(result["level"], "critical")
        self.assertGreaterEqual(result["score"], 100)
        self.assertTrue(any(reason.startswith("Quá hạn") for reason in result["reasons"]))

    def test_blocked_for_three_days_has_stuck_reason(self):
        result = priority_for(
            task(
                status="blocked",
                blocked_since=(NOW - timedelta(days=3)).isoformat(),
            ),
            NOW,
        )
        self.assertIn("Đang kẹt 3 ngày", result["reasons"])
        self.assertIn("Chia task", result["recommendation"])

    def test_due_soon_and_low_progress_gets_risk_boost(self):
        result = priority_for(
            task(due_at=(NOW + timedelta(days=1)).isoformat(), progress=20),
            NOW,
        )
        self.assertIn("Tiến độ dưới 50% gần deadline", result["reasons"])

    def test_done_task_is_sorted_last(self):
        tasks = [
            task(id=1, status="done", progress=100),
            task(id=2, due_at=(NOW + timedelta(days=20)).isoformat()),
            task(id=3, due_at=(NOW - timedelta(days=1)).isoformat()),
        ]
        ranked = enrich_and_rank(tasks, NOW)
        self.assertEqual([item["id"] for item in ranked], [3, 2, 1])

    def test_dashboard_builds_mock_discord_reminder(self):
        dashboard = build_dashboard(
            [task(due_at=(NOW - timedelta(hours=2)).isoformat())],
            NOW,
        )
        self.assertEqual(dashboard["summary"]["due_today_or_overdue"], 1)
        self.assertTrue(dashboard["discord_preview"]["is_mock"])
        self.assertIn("Task mẫu", dashboard["discord_preview"]["message"])


if __name__ == "__main__":
    unittest.main()
