"""BioSBOM-AgentKG: selected core and evidence-checked multi-agent runtime."""

from .risk import calculate_risk_score
from .schemas import AssetContext, Component, VEXStatus, Vulnerability

__version__ = "0.5.0"
__all__ = ["AssetContext", "Component", "VEXStatus", "Vulnerability", "calculate_risk_score"]
