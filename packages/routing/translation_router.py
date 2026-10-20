"""
TranslationRouter — deterministic provider/model routing.

Routing rules are sourced from config/routing.yaml so they can be
updated without touching Python code.
"""
from __future__ import annotations

from typing import Optional, Set, Tuple

from packages.core.config_loader import get_routing_config
from packages.routing.language import normalize_language_code
from packages.routing.policy import RoutingDecision


class TranslationRouter:
    def __init__(self) -> None:
        cfg = get_routing_config()
        self._policy_version: str = cfg.get("policy_version", "routing-v1")
        self._default_provider: str = cfg.get("default", {}).get("provider", "openrouter")
        self._default_model: str = cfg.get("default", {}).get(
            "model", "meta-llama/llama-3.3-70b-instruct"
        )

        # Build a set of (source, target) pairs per provider from routes
        self._provider_pairs: dict[str, Set[Tuple[str, str]]] = {}
        for route in cfg.get("routes", []):
            src = route["source"]
            provider = route["provider"]
            if provider not in self._provider_pairs:
                self._provider_pairs[provider] = set()
            for tgt in route.get("targets", []):
                self._provider_pairs[provider].add((src, tgt))

    # ------------------------------------------------------------------ #

    def _lookup_provider(self, src: str, tgt: str) -> Optional[str]:
        """Return the configured provider for a language pair, or None."""
        for provider, pairs in self._provider_pairs.items():
            if (src, tgt) in pairs:
                return provider
        return None

    def route(
        self,
        source_language: str,
        target_language: str,
        user_requested_provider: Optional[str] = None,
        circuit_open_providers: Optional[Set[str]] = None,
    ) -> RoutingDecision:
        """
        Resolve the best provider/model for a translation request.

        Priority order:
          1. User-requested provider (if circuit is closed)
          2. Routing table from routing.yaml (if circuit is closed)
          3. Default fallback (openrouter)
        """
        src = normalize_language_code(source_language)
        tgt = normalize_language_code(target_language)
        circuits = circuit_open_providers or set()

        # --- User override ---
        if user_requested_provider:
            if user_requested_provider not in circuits:
                return RoutingDecision(
                    source_language=src,
                    target_language=tgt,
                    provider=user_requested_provider,
                    model=self._default_model if user_requested_provider == "openrouter" else None,
                    reason="user_requested_provider",
                    policy_version=self._policy_version,
                )
            # Requested provider is circuit-open → fall through to table lookup

        # --- Routing table lookup ---
        table_provider = self._lookup_provider(src, tgt)
        if table_provider and table_provider not in circuits:
            model = self._default_model if table_provider == "openrouter" else None
            return RoutingDecision(
                source_language=src,
                target_language=tgt,
                provider=table_provider,
                model=model,
                reason="explicit_supported_language_pair",
                policy_version=self._policy_version,
            )


        # --- Default fallback ---
        return RoutingDecision(
            source_language=src,
            target_language=tgt,
            provider=self._default_provider,
            model=self._default_model,
            reason="default_fallback" if not table_provider else "circuit_open_fallback",
            policy_version=self._policy_version,
        )
