"""No-op decorators used purely as markers for pre-commit linters.

These do nothing at runtime — they exist so linters can detect intentional
exemptions via AST walk of decorator names.
"""

from collections.abc import Callable


def allow_single_ticker_fetcher[F: Callable[..., object]](func: F) -> F:
    """Mark a single-ticker fetcher as an intentional exemption.

    Checked by `scripts/hooks/check_no_single_ticker_fetcher.py`. Use only when
    the underlying API is genuinely single-symbol (e.g., vnstock fundamentals
    API, catalyst events API) and a batch version cannot be built without
    upstream API changes. Add an inline comment explaining why.
    """
    return func
