---
name: unit-test
description: Write, run, and fix unit tests following project patterns and best practices. Use when user asks to add tests, fix failing tests, review test quality, or increase coverage.
---

# Unit Test Skill

**Framework:** pytest + pytest-asyncio + pytest-mock
**Run:** `uv run pytest tests/unit/test_<module>.py -v --tb=short`
**Fixtures:** `tests/conftest.py` (shared mock data, async DB mocks, domain fixtures)

See `instructions.md` for the complete test workflow, mocking rules, and quality checklist.

## Templates

| Template | Use for |
|----------|---------|
| [templates/test_module.py](templates/test_module.py) | New test file with pure + async test patterns, parametrize, AAA structure |
