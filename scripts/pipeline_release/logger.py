"""Backward-compatible import for the shared pipeline logger."""
from pipeline_core.logger import PipelineLogger, logger
__all__=["PipelineLogger","logger"]
