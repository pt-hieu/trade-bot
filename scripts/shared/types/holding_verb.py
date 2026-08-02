"""Closed Literal of holding-decision verbs.

Lives in `shared/types/` (a leaf module) so both `pipeline.rendering.models`
(producer of `HoldingAction.verb`) and `shared.rules.synthesis_verb_match`
(verb-mismatch validator) can import without creating a pipeline → shared
back-edge. Re-exported from `pipeline.rendering.models` for back-compat.
"""

from __future__ import annotations

from typing import Literal

HoldingVerb = Literal["HOLD", "TRIM", "ADD", "EXIT", "EVALUATE"]
