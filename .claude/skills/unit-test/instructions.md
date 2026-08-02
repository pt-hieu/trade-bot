# Unit Test Instructions

Framework: pytest + pytest-asyncio + pytest-mock

---

## Step 1: Pre-Flight

Before writing any test:

1. **Read the function under test** — understand inputs, outputs, side effects, edge cases
2. **Check existing tests** — `tests/unit/test_<module>.py` may already cover some cases
3. **Check `tests/conftest.py`** for reusable fixtures — mock OHLCV data, async DB mocks, domain fixtures for portfolio/watchlist
4. **Classify the function:**
   - **Pure function** (deterministic, no I/O) → test directly, no mocks
   - **Async with DB/API** → mock at system boundaries
   - **File I/O** → use `tmp_path` fixture

## Step 2: Write Tests

### Structure: AAA Pattern (Always)

```python
def test_position_size_with_5pct_stop():
    # Arrange
    entry = 100_000
    stop = 95_000
    max_risk = 200_000

    # Act
    shares = compute_position_size(entry, stop, max_risk)

    # Assert
    assert shares == 40
```

### Naming Convention

```
File:     test_<module>.py
Class:    Test<FunctionOrConcept>
Function: test_<scenario>_<expected_outcome>
```

Examples:
- `test_trading_mode_below_5m_returns_low_cash`
- `test_classify_status_at_entry_zone_returns_buy_zone`
- `test_swing_detection_insufficient_data_returns_empty`

### Pattern Selection

| Situation | Pattern |
|-----------|---------|
| Multiple input/output combos | `@pytest.mark.parametrize` |
| Related tests for one function | Class grouping |
| Complex test data | Helper factory function |
| Async function with DB | `AsyncMock` + `@patch` |
| File system operations | `tmp_path` fixture |

### Parametrize for Multiple Cases

```python
@pytest.mark.parametrize("cash,expected", [
    (0, "REALLOCATION"),
    (3_000_000, "LOW_CASH"),
    (5_000_000, "LOW_CASH"),       # boundary
    (5_000_001, "NORMAL"),         # just above
    (25_000_000, "NORMAL"),
])
def test_trading_mode(cash, expected):
    assert determine_mode(cash) == expected
```

### Async Tests with Mocking

```python
from unittest.mock import AsyncMock, patch

class TestTradeSetup:
    @pytest.fixture
    def mock_ticker_data(self):
        with patch(
            "agents.tools.technicals.get_ticker_data_async",
            new_callable=AsyncMock
        ) as mock:
            mock.return_value = {"ticker": "TCB", "close": 35900}
            yield mock

    @pytest.mark.asyncio
    async def test_computes_rr_ratio(self, mock_ticker_data):
        result = await compute_trade_setup_async("TCB")
        assert result["rr_ratio"] >= 3.0
```

### Edge Cases — Systematic Checklist

Always test these boundaries:
- **Zero/empty**: `[]`, `{}`, `0`, `""`, `None`
- **One item**: Single element in collection
- **Exact thresholds**: Values at boundary (e.g., RSI exactly 30)
- **Just above/below**: Threshold ± 1 or ± 0.01
- **Missing optional fields**: Dict without expected keys
- **Invalid input**: Wrong types, negative values, NaN

## Step 3: Mocking Rules

### DO Mock (System Boundaries)
- Database queries (`shared.neon.*`, `shared.database.Database`)
- API calls (`shared.vnstock_client.*`)
- File I/O (`open`, `Path.read_text`)
- External services (Telegram, GitHub API)
- Time-dependent functions (`datetime.now`)

### DON'T Mock (Internal Logic)
- Pure calculation functions
- Data transformation helpers
- Format/parse utilities
- The function you're actually testing

### Mock Verification (When Side Effects Matter)
```python
async def test_alert_registered_with_correct_params(mock_db):
    await register_alert("FPT", "price_below", 95000)
    mock_db.assert_called_once_with(
        ticker="FPT",
        condition_type="price_below",
        condition_value=95000
    )
```

## Step 4: Run Tests

```bash
uv run pytest tests/unit/test_<module>.py -v --tb=short
uv run pytest tests/unit/test_<module>.py -k "test_name" -v
uv run pytest tests/ -v --tb=short -x    # stop on first failure
uv run pytest tests/ --cov=scripts --cov-report=term-missing
```

## Step 5: Fix Failing Tests

1. **Read the full error** — traceback, assertion message, expected vs actual
2. **Classify the failure:**
   - **Test bug**: Wrong assertion, stale mock, missing fixture → fix test
   - **Code bug**: Function returns wrong value → fix production code
   - **Environment**: Missing dep, wrong Python version → fix setup
3. **Fix and verify** — run the specific test again
4. **Never delete a failing test** — understand WHY it fails first
5. **If mock is stale**: Check if the production function signature changed

## Quality Checklist

- [ ] Each test follows AAA (Arrange/Act/Assert)
- [ ] Test names describe the behavior being tested
- [ ] Edge cases covered (None, empty, boundaries)
- [ ] No test interdependence (can run in any order)
- [ ] Mocks only at system boundaries
- [ ] No magic numbers without context (use named variables)
- [ ] `@pytest.mark.parametrize` used for >2 similar cases
- [ ] No `assert result` (truthy) — use specific assertions
- [ ] Tests fail when production code is broken (not just always-pass)

## Anti-Patterns to Avoid

| Anti-Pattern | Why Bad | Fix |
|-------------|---------|-----|
| `assert result` (truthy check) | Empty list passes, wrong type passes | `assert result == expected` |
| Testing `_private_method()` | Couples to implementation | Test through public API |
| Mocking what you're testing | Tests nothing | Mock dependencies, not SUT |
| Exact string matching | Breaks on formatting changes | `assert "key_content" in result` |
| Shared mutable state between tests | Order-dependent failures | Fresh fixtures per test |
| Complex test logic (if/for) | Test itself might have bugs | Keep tests linear and simple |
| Deleting failing test | Hides real bugs | Investigate root cause |

---

## Gotchas

- **`sys.path.insert(0, 'scripts')` for inline test runs.** Modules live under `scripts/`, not repo root. Without this, imports fail with `ModuleNotFoundError`.
- **Async fixtures need `@pytest_asyncio.fixture`, not `@pytest.fixture`.** Using the wrong decorator causes fixtures to return coroutine objects instead of resolved values.
- **Mock at `where-it's-used`, not `where-it's-defined`.** `@patch("agents.tools.technicals.get_ticker_data_async")`, not `@patch("shared.api.technicals.get_ticker_data_async")`. Python patches the name in the importing module's namespace.
- **Numpy types break assertions silently.** `numpy.float64(3.0) == 3.0` is True, but `assert result == {"value": 3.0}` can fail because numpy types don't match native Python types in dict comparisons. Cast to native types in test fixtures.
- **Never `assert result` (truthy check).** Empty list, empty dict, and 0 all pass truthy checks. Use `assert result == expected` with specific values.

---

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `dev-environment` | Running tests locally (pytest config, uv, conftest setup) |
| `agent-development` | Writing tests for agent tools or mocking agent config in tests |
| `data-layer` | Understanding how to mock `shared.neon.*` or `shared.api.*` calls at system boundaries |
