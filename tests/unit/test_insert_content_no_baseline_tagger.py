"""Regression — INSERT-time baseline substring tagger must stay deleted (SWI-390).

The v1 substring matcher in insert_content.py was tagging Ru-SSI-a /
g-REE-n / Ita-ly as SSI/REE/ITA. After SWI-390, articles.affected_tickers
is written exclusively by news_v2_persist (Stage-2). These three
assertions block accidental re-introduction at three different layers.
"""

from __future__ import annotations

import ast
import inspect


def test_extract_tickers_from_text_is_gone() -> None:
    """The buggy substring loop function must not be importable."""
    raised = False
    try:
        from shared.ticker_extract import extract_tickers_from_text  # noqa: F401
    except ImportError:
        raised = True
    assert raised, "extract_tickers_from_text should have been deleted from shared.ticker_extract"


def test_insert_content_module_does_not_expose_text_extractor() -> None:
    """insert_content must not re-export or import the deleted extractor."""
    import shared.neon.insert_content as m

    assert "extract_tickers_from_text" not in dir(m), (
        "shared.neon.insert_content unexpectedly exposes extract_tickers_from_text"
    )


def test_insert_content_no_company_tickers_for_loop() -> None:
    """AST walk: no `for ... in COMPANY_TICKERS` loop survives the file.

    Walks past comments + string literals so descriptive prose mentioning
    `COMPANY_TICKERS` doesn't false-positive.
    """
    import shared.neon.insert_content as m

    tree = ast.parse(inspect.getsource(m))
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            iter_src = ast.unparse(node.iter)
            assert "COMPANY_TICKERS" not in iter_src, (
                f"insert_content.py introduced a for-loop iterating COMPANY_TICKERS: {iter_src}"
            )
