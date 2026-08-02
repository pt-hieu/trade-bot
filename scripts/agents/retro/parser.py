#!/usr/bin/env python3
"""
Section constants for recommendation categorization.

Used by recommendation_builder.py and retro evaluation pipeline.
"""

from typing import Literal

# Canonical section values for recommendations
SECTION_WHAT_TO_DO = "WHAT_TO_DO"
SECTION_TOP_PICKS = "TOP_PICKS"
SECTION_MY_HOLDINGS = "MY_HOLDINGS"
SECTION_SKIP_THESE = "SKIP_THESE"
SECTION_LONG_TERM = "LONG_TERM"

SectionType = Literal["WHAT_TO_DO", "TOP_PICKS", "MY_HOLDINGS", "SKIP_THESE", "LONG_TERM"]
