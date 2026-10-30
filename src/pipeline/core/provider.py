"""Contract implemented by provider adapters."""
from __future__ import annotations
from typing import Mapping,Protocol,runtime_checkable
@runtime_checkable
class ProviderAdapter(Protocol):
    name:str
    def normalize_environment(self,environ:Mapping[str,str])->dict[str,str]:
        """Translate provider variables to the portable PIPELINE_* contract."""
        ...
