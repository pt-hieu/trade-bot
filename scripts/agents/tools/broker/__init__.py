"""Tool broker registry — public re-exports.

Post-SWI-180: tools are registered as native PydanticAI Tools via
`scripts/agents/tools/native_tools.py`. The legacy `ToolBroker` class +
`make_call_tools / make_search_tools / make_get_tool_schemas` meta-tools
are gone; this package now exists solely to host the registry, the domain
implementations, and the error-classification helpers consumed by
`native_tools._wrap_with_policy`.
"""

import logging

from .registry import ToolDomain, format_tool_listing

__all__ = [
    "ToolDomain",
    "format_tool_listing",
]

logger = logging.getLogger(__name__)

from . import domains as _domains  # noqa: E402, F401
