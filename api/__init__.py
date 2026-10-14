"""VocalLens FastAPI backend — a thin, typed API around the existing engine.

This package does NOT reimplement any analysis. It imports and calls the
canonical `vocallens.pipeline.analyze_pair` and the existing exporters, and
adapts their validated output to HTTP at the boundary.
"""
