"""Controlled document ownership rules shared by every history endpoint."""

VALUATION_DOCUMENT_TYPES = frozenset(
    {
        "candidate-confirmation-export",
        "generated-draft-report",
        "generated-report",
        "complete-valuation-report",
    }
)

REVIEW_DOCUMENT_TYPES = frozenset({"review-report", "correction-request"})
