import json
import time
from typing import Any, Dict, List, Optional

from packages.core.config_loader import get_limits_config


def _rates() -> tuple[float, float]:
    c = get_limits_config().get("cost_estimation", {})
    return float(c.get("cost_per_1k_input_tokens", 0.0007)), float(c.get("cost_per_1k_output_tokens", 0.0009))


def usd_for(input_tokens: int, output_tokens: int) -> float:
    r_in, r_out = _rates()
    return (input_tokens * r_in + output_tokens * r_out) / 1000.0


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3 * 2.5)) if text else 0


class CostCollector:
    """Accumulates per-call cost entries during one operation."""

    def __init__(self, kind: str):
        self.kind = kind
        self.entries: List[Dict[str, Any]] = []

    def add(self, provider: str, model: str, input_tokens: int, output_tokens: int,
            cost_usd: Optional[float] = None, estimated: bool = False, purpose: Optional[str] = None) -> None:
        if cost_usd is None:
            cost_usd = usd_for(input_tokens, output_tokens)
            estimated = True
        self.entries.append({
            "kind": self.kind, "purpose": purpose or self.kind, "provider": provider, "model": model,
            "input_tokens": int(input_tokens), "output_tokens": int(output_tokens),
            "cost_usd": round(float(cost_usd), 6), "estimated": estimated,
        })

    def add_llm_response(self, response: Dict[str, Any], purpose: str) -> None:
        u = response.get("usage") or {}
        self.add("openrouter", response.get("model", "unknown"), u.get("prompt_tokens", 0),
                 u.get("completion_tokens", 0), purpose=purpose)

    @property
    def total(self) -> float:
        return round(sum(e["cost_usd"] for e in self.entries), 6)


class CostLedger:
    def __init__(self, storage):
        self.storage = storage

    @staticmethod
    def key(document_id: str) -> str:
        return f"documents/{document_id}/costs.json"

    async def load(self, document_id: str) -> List[Dict[str, Any]]:
        k = self.key(document_id)
        if not await self.storage.exists(k):
            return []
        return json.loads((await self.storage.get_object(k)).decode("utf-8"))

    async def record(self, document_id: str, collector: CostCollector, version_id: Optional[str] = None) -> None:
        if not collector.entries:
            return
        rows = await self.load(document_id)
        ts = time.time()
        for e in collector.entries:
            rows.append({**e, "ts": ts, "version_id": version_id})
        await self.storage.put_object(self.key(document_id), json.dumps(rows).encode("utf-8"), "application/json")

    async def summary(self, document_id: str) -> Dict[str, Any]:
        rows = await self.load(document_id)
        by_kind: Dict[str, float] = {}
        for r in rows:
            by_kind[r["kind"]] = by_kind.get(r["kind"], 0.0) + r["cost_usd"]
        return {
            "document_id": document_id,
            "total_usd": round(sum(r["cost_usd"] for r in rows), 6),
            "translate_usd": round(by_kind.get("translate", 0.0), 6),
            "edit_usd": round(by_kind.get("edit", 0.0), 6),
            "calls": len(rows),
            "has_estimates": any(r.get("estimated") for r in rows),
        }
