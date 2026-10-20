import os
from typing import Optional
from packages.routing.policy import OCRDecision


class OCRRouter:
    def __init__(self, primary_provider: Optional[str] = None, fallback_provider: Optional[str] = None):
        self.primary = primary_provider or os.getenv("OCR_PROVIDER", "bodhan")
        self.fallback = fallback_provider or os.getenv("OCR_FALLBACK_PROVIDER", "pymupdf")

    def route(self, circuit_open_providers: Optional[set] = None) -> OCRDecision:
        circuits = circuit_open_providers or set()
        if self.primary not in circuits:
            return OCRDecision(
                provider=self.primary,
                fallback_provider=self.fallback,
                reason="configured_primary_provider",
            )
        return OCRDecision(
            provider=self.fallback,
            fallback_provider=None,
            reason="primary_circuit_open_fallback",
        )
