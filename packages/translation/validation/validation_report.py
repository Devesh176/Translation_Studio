from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import time
from packages.translation.validation.validation_issue import GateStatus, ValidationIssue, IssueSeverity


class GateResult(BaseModel):
    status: GateStatus = GateStatus.NOT_RUN
    issue_count: int = 0
    issues: List[ValidationIssue] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    job_id: str
    source_language: str
    target_language: str
    policy_version: str = "2.0"
    overall_status: GateStatus = GateStatus.PASS
    gates: Dict[str, GateResult] = Field(default_factory=lambda: {
        "preflight": GateResult(),
        "source_ir": GateResult(),
        "protected_spans": GateResult(),
        "translation": GateResult(),
        "facts": GateResult(),
        "translated_ir": GateResult(),
        "typography": GateResult(),
        "pdf_round_trip": GateResult(),
        "visual_qa": GateResult(),
        "release": GateResult(),
    })
    block_results: List[Dict[str, Any]] = Field(default_factory=list)
    issues: List[ValidationIssue] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)

    def record_issue(self, gate_name: str, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        if gate_name not in self.gates:
            self.gates[gate_name] = GateResult()
        
        gate = self.gates[gate_name]
        gate.issues.append(issue)
        gate.issue_count += 1

        if issue.severity == IssueSeverity.CRITICAL:
            gate.status = GateStatus.FAIL
        elif issue.severity in [IssueSeverity.HIGH, IssueSeverity.ERROR] and gate.status != GateStatus.FAIL:
            gate.status = GateStatus.REVIEW_REQUIRED
        elif issue.severity in [IssueSeverity.MEDIUM, IssueSeverity.WARNING] and gate.status not in [GateStatus.FAIL, GateStatus.REVIEW_REQUIRED]:
            gate.status = GateStatus.REVIEW_REQUIRED

        self._recompute_overall_status()

    def set_gate_status(self, gate_name: str, status: GateStatus, metrics: Optional[Dict[str, Any]] = None) -> None:
        if gate_name not in self.gates:
            self.gates[gate_name] = GateResult()
        self.gates[gate_name].status = status
        if metrics:
            self.gates[gate_name].metrics.update(metrics)
        self._recompute_overall_status()

    def _recompute_overall_status(self) -> None:
        statuses = [g.status for g in self.gates.values() if g.status != GateStatus.NOT_RUN]
        if any(s == GateStatus.FAIL for s in statuses):
            self.overall_status = GateStatus.FAIL
        elif any(s == GateStatus.REVIEW_REQUIRED for s in statuses):
            self.overall_status = GateStatus.REVIEW_REQUIRED
        elif any(s == GateStatus.RETRY for s in statuses):
            self.overall_status = GateStatus.RETRY
        elif all(s == GateStatus.PASS for s in statuses) and len(statuses) > 0:
            self.overall_status = GateStatus.PASS
        else:
            self.overall_status = GateStatus.NOT_RUN
