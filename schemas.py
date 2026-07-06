"""Pydantic models for structured extraction from Maryland OLA audit reports.

These schemas are passed to the LLM (via the llm library's schema support) to
constrain output, and used to validate what comes back. Report type is NOT
extracted by the LLM -- it comes from ola_reports.json metadata.
"""
from typing import Literal

from pydantic import BaseModel


class DollarAmount(BaseModel):
    """A dollar figure mentioned in a finding, with surrounding context."""
    amount: float
    context: str


class Finding(BaseModel):
    """A single numbered finding ("Finding N") from an OLA audit report."""
    number: int
    title: str  # the bold summary sentence that opens the finding
    description: str  # 1-3 sentence summary of the Analysis section
    category: Literal[
        "cash_receipts",
        "payroll",
        "procurement_disbursements",
        "information_systems_security",
        "grants_monitoring",
        "equipment_inventory",
        "corporate_purchasing_cards",
        "contract_monitoring",
        "federal_funds",
        "accounts_receivable",
        "other",
    ]
    is_repeat: bool
    prior_finding_number: int | None
    dollar_amounts: list[DollarAmount]
    recommendation: str | None
    agency_agrees: bool | None
    agency_completion_date: str | None


class ReportExtraction(BaseModel):
    """Document-level extraction for one OLA audit report."""
    agency_name: str
    parent_department: str | None
    report_date: str | None  # letter date IN the document -- don't trust metadata
    audit_period_start: str | None
    audit_period_end: str | None
    findings: list[Finding]
    prior_findings_count: int | None
    prior_findings_repeated: int | None
    criminal_referral: bool  # true only if a matter WAS actually referred
    fraud_hotline_origin: bool
    agency_response_summary: str
    total_dollar_impact: float | None
    extraction_notes: str | None


class FindingsChunk(BaseModel):
    """Findings-only schema used for chunks 2..N of very large reports.

    Document-level fields come from chunk 1 (which always contains the
    transmittal letter); later chunks only contribute findings.
    """
    findings: list[Finding]
