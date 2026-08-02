"""Tests for scripts/collect_review_data.py."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import pytest

# Import after conftest.py adds scripts/ to sys.path
from collect_review_data import (
    CRITICAL_QUERIES,
    _parse_brief_sections,
    json_serial,
    write_json,
)


class TestJsonSerial:
    def test_date(self):
        assert json_serial(date(2026, 4, 2)) == "2026-04-02"

    def test_datetime(self):
        result = json_serial(datetime(2026, 4, 2, 10, 30, tzinfo=UTC))
        assert "2026-04-02" in result

    def test_decimal(self):
        assert json_serial(Decimal("42.5")) == 42.5

    def test_uuid(self):
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        assert json_serial(test_uuid) == str(test_uuid)

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError, match="not serializable"):
            json_serial(set())


class TestWriteJson:
    def test_writes_list(self, tmp_path):
        data = [{"ticker": "FPT", "price": 145000}]
        count = write_json(tmp_path, "test.json", data)
        assert count == 1
        loaded = json.loads((tmp_path / "test.json").read_text())
        assert loaded[0]["ticker"] == "FPT"

    def test_writes_dict(self, tmp_path):
        data = {"regime": "RISK_ON"}
        count = write_json(tmp_path, "test.json", data)
        assert count == 1

    def test_writes_empty_list(self, tmp_path):
        count = write_json(tmp_path, "test.json", [])
        assert count == 0

    def test_writes_none(self, tmp_path):
        count = write_json(tmp_path, "test.json", None)
        assert count == 0

    def test_serializes_dates(self, tmp_path):
        data = [{"scan_date": date(2026, 4, 2)}]
        write_json(tmp_path, "test.json", data)
        loaded = json.loads((tmp_path / "test.json").read_text())
        assert loaded[0]["scan_date"] == "2026-04-02"

    def test_serializes_decimals(self, tmp_path):
        data = [{"pnl": Decimal("3.14")}]
        write_json(tmp_path, "test.json", data)
        loaded = json.loads((tmp_path / "test.json").read_text())
        assert loaded[0]["pnl"] == 3.14

    def test_writes_dict_of_tickers_returns_len(self, tmp_path):
        """Registry-shaped dicts (all values are dicts) report ticker count."""
        data = {
            "FPT": {"sector": "tech", "score": 0.8},
            "VCB": {"sector": "banking", "score": 0.7},
        }
        count = write_json(tmp_path, "watchlist.json", data)
        assert count == 2

    def test_writes_struct_dict_returns_one(self, tmp_path):
        """Mixed-value-type dicts (manifest-style) still return 1."""
        data = {"date": "2026-04-27", "scope": "full"}
        count = write_json(tmp_path, "manifest.json", data)
        assert count == 1


class TestParseBriefSections:
    def test_matches_hash_prefixed_header(self):
        text = "## GLOBAL MACRO\n- DXY: 98\n## COMMODITIES\n- oil: $96"
        sections = _parse_brief_sections(text)
        assert set(sections.keys()) == {"GLOBAL MACRO", "COMMODITIES"}
        assert "- DXY: 98" in sections["GLOBAL MACRO"]
        assert "- oil: $96" in sections["COMMODITIES"]

    def test_matches_bare_caps_header(self):
        text = "TODAY'S THEME\nbody text here"
        sections = _parse_brief_sections(text)
        assert "TODAY'S THEME" in sections
        assert sections["TODAY'S THEME"] == "body text here"

    def test_matches_mixed_brief(self):
        """LLM-authored bare caps + news_digest ## headers in same body."""
        text = (
            "## GLOBAL MACRO\n- DXY: 98\n"
            "TODAY'S THEME\nrotation into banks\n"
            "## VN ECONOMY\n- CPI: 3.1%"
        )
        sections = _parse_brief_sections(text)
        assert "GLOBAL MACRO" in sections
        assert "TODAY'S THEME" in sections
        assert "VN ECONOMY" in sections


class TestCriticalQueries:
    def test_daily_record_is_critical(self):
        assert "daily_record" in CRITICAL_QUERIES

    def test_recommendations_is_critical(self):
        assert "recommendations" in CRITICAL_QUERIES

    def test_watchlist_is_not_critical(self):
        assert "watchlist_swing" not in CRITICAL_QUERIES


class TestFetchGitFixes:
    def test_returns_empty_on_no_commits(self, tmp_path):
        from collect_review_data import fetch_git_fixes

        result = fetch_git_fixes("2099-01-01", str(tmp_path))
        assert result == []

    def test_returns_empty_on_invalid_repo(self):
        from collect_review_data import fetch_git_fixes

        result = fetch_git_fixes("2026-04-02", "/nonexistent")
        assert result == []


class TestFetchGhActions:
    @patch("collect_review_data.subprocess.run")
    def test_returns_empty_on_gh_failure(self, mock_run):
        from collect_review_data import fetch_gh_actions

        mock_run.return_value = type("Result", (), {"returncode": 1, "stdout": ""})()
        result = fetch_gh_actions("2026-04-02", "full")
        assert result["runs"] == []

    @patch("collect_review_data.subprocess.run")
    def test_parses_valid_gh_output(self, mock_run):
        from collect_review_data import fetch_gh_actions

        mock_run.return_value = type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": json.dumps(
                    [
                        {
                            "databaseId": 123,
                            "status": "completed",
                            "conclusion": "success",
                            "startedAt": "2026-04-02T00:00:00Z",
                            "updatedAt": "2026-04-02T01:30:00Z",
                            "headBranch": "main",
                        }
                    ]
                ),
            },
        )()
        result = fetch_gh_actions("2026-04-02", "morning")
        assert len(result["runs"]) == 1
        assert result["runs"][0]["databaseId"] == 123
        assert result["runs"][0]["workflow"] == "daily-scan.yml"
