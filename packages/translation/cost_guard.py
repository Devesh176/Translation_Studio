"""
CostGuard — enforces per-document translation cost limits.

All thresholds are sourced from config/limits.yaml so they can be tuned
without touching Python code.  Script-aware token multipliers compensate
for the fact that standard English BPE tokenizers heavily undercount
UTF-8 multi-byte Indic glyphs.
"""
from __future__ import annotations

import os
from packages.core.exceptions import CostLimitExceededError
from packages.core.config_loader import get_limits_config
from packages.translation.chunker import TranslationChunker
from packages.routing.language import detect_unicode_script, normalize_language_code, get_language_registry


class CostGuard:
    def __init__(self, max_translation_cost_usd=None) -> None:
        cfg = get_limits_config()
        limits = cfg.get("limits", {})
        cost_cfg = cfg.get("cost_estimation", {})

        # Max allowed spend per translation request (explicit param -> env -> limits.yaml)
        if max_translation_cost_usd is not None:
            self.max_cost: float = float(max_translation_cost_usd)
        else:
            self.max_cost = float(
                os.getenv(
                    "MAX_TRANSLATION_COST_USD",
                    limits.get("max_translation_cost_usd", 1.00),
                )
            )


        # Token pricing (OpenRouter meta-llama/llama-3.3-70b-instruct)
        self.cost_per_1k_input: float = float(
            cost_cfg.get("cost_per_1k_input_tokens", 0.0007)
        )
        self.cost_per_1k_output: float = float(
            cost_cfg.get("cost_per_1k_output_tokens", 0.0009)
        )

        # Script-aware token multipliers from limits.yaml
        self._multipliers: dict[str, float] = cost_cfg.get(
            "script_token_multipliers",
            {
                "Latin": 1.0,
                "Devanagari": 2.5,
                "Tamil": 3.0,
                "Telugu": 3.0,
                "Kannada": 3.0,
                "Malayalam": 3.0,
                "Bengali": 2.8,
                "Gujarati": 2.8,
                "Gurmukhi": 2.8,
                "Default": 2.5,
            },
        )

    # ------------------------------------------------------------------ #

    def _token_multiplier(self, script: str) -> float:
        return self._multipliers.get(script, self._multipliers.get("Default", 2.5))

    def check_and_estimate_cost(self, text: str, target_language: str) -> float:
        """
        Estimate the USD cost of translating *text* to *target_language* and raise
        CostLimitExceededError if it exceeds the configured budget.

        Returns the estimated cost on success.
        """
        registry = get_language_registry()
        tgt_code = normalize_language_code(target_language)
        tgt_info = registry.get(tgt_code)
        target_script = tgt_info.script if tgt_info else "Devanagari"
        tgt_multiplier = self._token_multiplier(target_script)

        src_script, _ = detect_unicode_script(text)
        src_multiplier = self._token_multiplier(src_script)

        words = len(text.split())
        base_tokens = max(1, int(words * 1.3))

        inp_tokens = int(base_tokens * src_multiplier)
        out_tokens = int(base_tokens * tgt_multiplier * 1.2)

        estimated_cost = (
            inp_tokens * self.cost_per_1k_input
            + out_tokens * self.cost_per_1k_output
        ) / 1000.0

        if estimated_cost > self.max_cost:
            raise CostLimitExceededError(
                f"Estimated cost ${estimated_cost:.4f} exceeds budget ${self.max_cost:.2f}",
                details={
                    "estimated_cost_usd": estimated_cost,
                    "max_allowed_usd": self.max_cost,
                    "input_tokens": inp_tokens,
                    "output_tokens": out_tokens,
                    "src_script": src_script,
                    "target_script": target_script,
                },
            )

        return estimated_cost

