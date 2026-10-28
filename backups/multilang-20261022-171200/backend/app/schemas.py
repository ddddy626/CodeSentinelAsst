from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["S0", "S1", "S2", "S3"]
EvidenceLevel = Literal["strong", "medium", "weak"]
Disposition = Literal["must_fix", "suggested", "uncertain"]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    filename: str = "source.py"
    source: str = Field(min_length=1)


class ToolCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    rule_id: str
    title: str
    explanation: str
    line: int = Field(ge=1)
    severity: Severity
    tool: str
    evidence: str
    suggestion: str
    trigger_path: str | None = None


class ModelCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    rule_id: str
    title: str
    explanation: str
    line: int = Field(ge=1)
    code_quote: str
    severity: Severity
    suggestion: str


class ArchitectAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    finding_id: str
    assessment: Literal["supported", "disputed", "unknown"]
    reason: str = Field(min_length=1, max_length=500)


class ScanResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: str = "1"
    task_id: str | None = None
    rule_version: str = "v1-1"
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    filename: str
    tool_drafts: list[ToolCandidate]
    model_drafts: list[ModelCandidate]
    completed: list[str]
    gaps: list[str]
    context_ranges: list[tuple[int, int]]
    omitted_ranges: list[tuple[int, int]]
    original_chars: int
    selected_chars: int


class Evidence(BaseModel):
    origin: Literal["tool", "llm", "source"]
    source: str
    detail: str


class Verification(BaseModel):
    status: Literal["tool_reported", "located", "corroborated"]
    reason: str


class Finding(BaseModel):
    id: str
    rule_id: str
    title: str
    explanation: str
    line: int = Field(ge=1)
    severity: Severity
    evidence_level: EvidenceLevel
    disposition: Disposition
    evidence: list[Evidence]
    suggestion: str
    verification: Verification | None = None
    trigger_path: str | None = None


class Coverage(BaseModel):
    completed: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ReviewReport(BaseModel):
    id: str
    task_id: str | None = None
    filename: str
    created_at: str
    decision: Literal["request_changes", "comment", "pass"]
    findings: list[Finding]
    coverage: Coverage
    rule_version: str = "v1-1"
    source_hash: str | None = None
    model_version: str | None = None
    context_ranges: list[tuple[int, int]] = Field(default_factory=list)
    omitted_ranges: list[tuple[int, int]] = Field(default_factory=list)
    context_chars: int | None = None
    build_version: str = "v1-1"
