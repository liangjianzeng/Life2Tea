"""
gateway — Unified Model Gateway for Life2Tea.

Consolidates the three previously-disconnected inference paths
(chat_router + SystemRouter, proxy_service + DynamicModelManager, dead
openai_proxy.py) into a single provider-abstraction + router + OpenAI-compatible
API. Providers are configured declaratively (config/gateway.json), not via the
legacy plugin-manifest system.
"""

from .providers.base import (
    Provider,
    ProviderKind,
    ProviderSpec,
    ModelEndpoint,
    EndpointStatus,
    GatewayError,
)
from .manager import ProviderManager
from .router import GatewayRouter

__all__ = [
    "Provider",
    "ProviderKind",
    "ProviderSpec",
    "ModelEndpoint",
    "EndpointStatus",
    "GatewayError",
    "ProviderManager",
    "GatewayRouter",
]
