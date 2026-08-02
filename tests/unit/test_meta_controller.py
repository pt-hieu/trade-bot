"""Tests for meta-controller workflow routing rules."""

import pytest

from agents.meta_controller import WorkflowType, determine_workflow, get_workflow_config


class TestMetaControllerRouting:
    """Routing rules fire in the correct order with correct outputs."""

    def test_normal_trading_day_routes_to_full_workflow(self):
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="RISK_ON",
            global_macro_regime="CALM",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=50_000_000,
        )
        assert decision.workflow == WorkflowType.FULL
        assert decision.skip_agents == []
        assert decision.priority_agents == []

    def test_non_trading_day_routes_to_research_with_sectors(self):
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_macro_regime="CALM",
            is_trading_day=False,
            urgent_exits=0,
            deployable_cash=50_000_000,
        )
        assert decision.workflow == WorkflowType.RESEARCH
        # Sectors run for Monday prep (systemic intelligence)
        assert "sector_analysis" not in decision.skip_agents
        assert "sector_analysis" in decision.priority_agents
        assert "positions" in decision.skip_agents
        assert "synthesis" in decision.skip_agents
        assert "macro" in decision.priority_agents

    def test_crisis_macro_regime_routes_to_exit_only_with_sectors(self):
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="RISK_OFF",
            global_macro_regime="CRISIS",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=50_000_000,
        )
        assert decision.workflow == WorkflowType.EXIT_ONLY
        # Sectors run — news catalysts inform exit timing
        assert "sector_analysis" not in decision.skip_agents
        assert "sector_analysis" in decision.priority_agents
        assert "longterm" in decision.skip_agents
        assert "foreign_flow" in decision.skip_agents
        assert "positions" in decision.priority_agents
        assert "market_level" in decision.priority_agents

    def test_low_cash_with_zero_deployable_routes_to_exit_only_with_sectors(self):
        decision = determine_workflow(
            trading_mode="LOW_CASH",
            market_regime="NEUTRAL",
            global_macro_regime="CALM",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=0,
        )
        assert decision.workflow == WorkflowType.EXIT_ONLY
        # Sectors run for systemic context even with no cash
        assert "sector_analysis" not in decision.skip_agents
        assert "sector_analysis" in decision.priority_agents
        assert "longterm" in decision.skip_agents
        assert "positions" in decision.priority_agents

    def test_elevated_macro_regime_routes_to_full_with_elevated_quality_bar(self):
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_macro_regime="ELEVATED",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=50_000_000,
        )
        assert decision.workflow == WorkflowType.FULL
        assert decision.skip_agents == []
        assert "positions" in decision.priority_agents
        assert "macro" in decision.priority_agents
        assert "market_level" in decision.priority_agents

    def test_risk_off_market_regime_routes_to_full_with_elevated_quality_bar(self):
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="RISK_OFF",
            global_macro_regime="CAUTIOUS",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=50_000_000,
        )
        assert decision.workflow == WorkflowType.FULL
        assert decision.skip_agents == []
        assert "positions" in decision.priority_agents
        assert "macro" in decision.priority_agents
        assert "market_level" in decision.priority_agents

    def test_urgent_exits_routes_to_quick_workflow(self):
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_macro_regime="CALM",
            is_trading_day=True,
            urgent_exits=2,
            deployable_cash=50_000_000,
        )
        assert decision.workflow == WorkflowType.QUICK
        assert "longterm" in decision.skip_agents
        assert "foreign_flow" in decision.skip_agents
        assert "positions" in decision.priority_agents

    def test_reallocation_mode_routes_to_full_with_exit_focus(self):
        decision = determine_workflow(
            trading_mode="REALLOCATION",
            market_regime="NEUTRAL",
            global_macro_regime="CALM",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=0,
        )
        assert decision.workflow == WorkflowType.FULL
        assert decision.skip_agents == []
        assert "positions" in decision.priority_agents
        assert "sector_analysis" in decision.priority_agents

    def test_low_cash_with_deployable_skips_research_agents(self):
        decision = determine_workflow(
            trading_mode="LOW_CASH",
            market_regime="NEUTRAL",
            global_macro_regime="CALM",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=3_000_000,
        )
        assert decision.workflow == WorkflowType.FULL
        assert "longterm" in decision.skip_agents
        assert "foreign_flow" in decision.skip_agents
        assert "positions" in decision.priority_agents
        assert "sector_analysis" in decision.priority_agents

    def test_low_cash_with_deployable_context_summary_includes_cash_amount(self):
        deployable_cash = 3_500_000
        decision = determine_workflow(
            trading_mode="LOW_CASH",
            market_regime="NEUTRAL",
            global_macro_regime="CALM",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=deployable_cash,
        )
        assert "3500000" in decision.context_summary or "LOW_CASH" in decision.context_summary

    def test_default_normal_conditions_routes_to_full_workflow(self):
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_macro_regime="CAUTIOUS",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=50_000_000,
        )
        assert decision.workflow == WorkflowType.FULL
        assert decision.skip_agents == []
        assert decision.priority_agents == []


class TestWorkflowConfig:
    """Workflow configs correctly map booleans for each workflow type."""

    @pytest.mark.parametrize(
        "workflow,expected_sectors",
        [
            (WorkflowType.FULL, True),
            (WorkflowType.EXIT_ONLY, True),
            (WorkflowType.RESEARCH, True),
            (WorkflowType.QUICK, False),
        ],
    )
    def test_sectors_always_on_except_quick(self, workflow, expected_sectors):
        config = get_workflow_config(workflow)
        assert config["run_sectors"] is expected_sectors

    @pytest.mark.parametrize(
        "workflow,expected_positions",
        [
            (WorkflowType.FULL, True),
            (WorkflowType.EXIT_ONLY, True),
            (WorkflowType.QUICK, True),
            (WorkflowType.RESEARCH, False),
        ],
    )
    def test_positions_off_only_in_research(self, workflow, expected_positions):
        config = get_workflow_config(workflow)
        assert config["run_positions"] is expected_positions

    def test_full_workflow_runs_all_agents(self):
        config = get_workflow_config(WorkflowType.FULL)
        assert config["run_sectors"] is True
        assert config["run_longterm"] is False
        assert config["run_positions"] is True
        assert config["run_foreign_flow"] is True

    def test_quick_workflow_minimal_agents(self):
        config = get_workflow_config(WorkflowType.QUICK)
        assert config["run_sectors"] is False
        assert config["run_longterm"] is False
        assert config["run_positions"] is True
        assert config["run_foreign_flow"] is False

    def test_unknown_workflow_falls_back_to_full(self):
        config = get_workflow_config("nonexistent")
        assert config["run_sectors"] is True
        assert config["run_longterm"] is False


class TestRulePriority:
    """Rules fire in correct priority order when multiple conditions match."""

    def test_crisis_overrides_urgent_exits(self):
        """CRISIS (rule 2) takes precedence over urgent exits (rule 5)."""
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="RISK_OFF",
            global_macro_regime="CRISIS",
            is_trading_day=True,
            urgent_exits=3,
            deployable_cash=50_000_000,
        )
        assert decision.workflow == WorkflowType.EXIT_ONLY

    def test_non_trading_day_overrides_crisis(self):
        """Non-trading day (rule 1) takes precedence over CRISIS (rule 2)."""
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="RISK_OFF",
            global_macro_regime="CRISIS",
            is_trading_day=False,
            urgent_exits=3,
            deployable_cash=0,
        )
        assert decision.workflow == WorkflowType.RESEARCH

    def test_low_cash_zero_overrides_elevated(self):
        """LOW_CASH/0 (rule 3) takes precedence over ELEVATED (rule 4)."""
        decision = determine_workflow(
            trading_mode="LOW_CASH",
            market_regime="NEUTRAL",
            global_macro_regime="ELEVATED",
            is_trading_day=True,
            urgent_exits=0,
            deployable_cash=0,
        )
        assert decision.workflow == WorkflowType.EXIT_ONLY

    def test_elevated_overrides_urgent_exits(self):
        """ELEVATED (rule 4) takes precedence over urgent exits (rule 5)."""
        decision = determine_workflow(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_macro_regime="ELEVATED",
            is_trading_day=True,
            urgent_exits=2,
            deployable_cash=50_000_000,
        )
        assert decision.workflow == WorkflowType.FULL
