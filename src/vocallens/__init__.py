"""VocalLens: evidence-grounded contrastive speech-delivery analysis.

See ARCHITECTURE.md (canonical for algorithms/contracts) and DESIGN.md
(canonical for UX). The single public entry point is
:func:`vocallens.pipeline.analyze_pair`.
"""
from __future__ import annotations

__version__ = "0.1.0"

# Serialized-result schema version. Bump (with a migration note) whenever the
# serialized AnalysisResult shape changes — see CLAUDE.md §2 contract-change rule.
SCHEMA_VERSION = 1

__all__ = ["__version__", "SCHEMA_VERSION"]
