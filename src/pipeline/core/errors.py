"""Typed pipeline errors."""
class PipelineError(RuntimeError): pass
class PipelineConfigError(PipelineError): pass
class ArtifactError(PipelineError): pass
