"""Self-tests for the post-LLM emit AST guard (SWI-206 Layer B)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from precommit.check_post_llm_emit import _check_file


def _write(tmp_path: Path, src: str, name: str = "agents/dummy.py") -> Path:
    """Write under a fake repo layout matching the guard's TARGET_PREFIX."""
    repo = tmp_path / "scripts"
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(src))
    return target


@pytest.fixture(autouse=True)
def _patch_repo_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("precommit.check_post_llm_emit.REPO_ROOT", tmp_path)


def test_setattr_without_emit_fails(tmp_path: Path) -> None:
    src = """
    from pydantic import BaseModel, model_validator
    class Foo(BaseModel):
        bar: str
        @model_validator(mode="after")
        def fix(self):
            object.__setattr__(self, "bar", "x")
            return self
    """
    findings = _check_file(_write(tmp_path, src), allowlist=set())
    assert findings, "expected guard failure"


def test_helper_delegated_mutation_fails(tmp_path: Path) -> None:
    src = """
    from pydantic import BaseModel, model_validator
    def _do(model):
        model.bar = "x"
    class Foo(BaseModel):
        bar: str
        @model_validator(mode="after")
        def fix(self):
            _do(self)
            return self
    """
    findings = _check_file(_write(tmp_path, src), allowlist=set())
    assert findings, "expected guard failure on helper-delegated mutation"


def test_field_validator_attribute_assign_fails(tmp_path: Path) -> None:
    src = """
    from pydantic import BaseModel, field_validator
    class Foo(BaseModel):
        bar: int = 0
        @field_validator("bar")
        def fix(cls, v):
            cls.bar = v + 1
            return v
    """
    findings = _check_file(_write(tmp_path, src), allowlist=set())
    assert findings, "expected guard failure on @field_validator"


def test_emit_present_passes(tmp_path: Path) -> None:
    src = """
    from pydantic import BaseModel, model_validator
    def emit_rule_outcome(*a, **k): pass
    class Foo(BaseModel):
        bar: str
        @model_validator(mode="after")
        def fix(self):
            object.__setattr__(self, "bar", "x")
            emit_rule_outcome("x", "coerced", agent="t")
            return self
    """
    findings = _check_file(_write(tmp_path, src), allowlist=set())
    assert findings == []


def test_allowlisted_passes(tmp_path: Path) -> None:
    src = """
    from pydantic import BaseModel, model_validator
    class Foo(BaseModel):
        bar: str
        @model_validator(mode="after")
        def fix(self):
            object.__setattr__(self, "bar", "x")
            return self
    """
    path = _write(tmp_path, src)
    allow = {"scripts/agents/dummy.py:Foo.fix"}
    findings = _check_file(path, allowlist=allow)
    assert findings == []
