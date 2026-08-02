"""Shared type aliases for tool implementations.

`RequiredTickers` is the canonical annotation for any tool parameter that
demands a non-empty ticker list. Native PydanticAI surfaces the
`Len(min_length=1)` constraint via JSON Schema (`minItems: 1`) so the model
boundary rejects `tickers=[]` emissions identically to a missing key —
closing the empty-list bypass surfaced by the SWI-180 Stage 0 spike.
"""

from __future__ import annotations

from typing import Annotated

from annotated_types import Len

RequiredTickers = Annotated[list[str], Len(min_length=1)]
