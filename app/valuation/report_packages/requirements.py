from dataclasses import dataclass


REPORT_COMPARISON_COMMERCIAL = "REPORT_COMPARISON_COMMERCIAL"
REPORT_ROOT_FORM_CODE = "F02"
REPORT_SCHEMA_VERSION = "report-comparison-commercial-v1"


@dataclass(frozen=True)
class ReportPageDefinition:
    code: str
    name: str
    kind: str
    form_code: str | None = None
    document_type: str | None = None


@dataclass(frozen=True)
class ReportPackageDefinition:
    report_type: str
    name: str
    land_use_type: str
    valuation_method: str
    pages: tuple[ReportPageDefinition, ...]


REPORT_PACKAGES = {
    REPORT_COMPARISON_COMMERCIAL: ReportPackageDefinition(
        report_type=REPORT_COMPARISON_COMMERCIAL,
        name="商業用地比較法完整查估書",
        land_use_type="COMMERCIAL",
        valuation_method="COMPARISON",
        pages=(
            ReportPageDefinition(
                code="S01",
                name="地價區段勘查表",
                kind="FORM",
                form_code="S01",
            ),
            ReportPageDefinition(
                code="F02-RF",
                name="影響地價區域因素分析明細表（商業用地）",
                kind="FORM",
                form_code="F02-RF",
            ),
            ReportPageDefinition(
                code="F02",
                name="比較法調查估價表",
                kind="FORM",
                form_code="F02",
            ),
            ReportPageDefinition(
                code="MAP-01",
                name="地價區段略圖",
                kind="DOCUMENT",
                document_type="map-section-sketch",
            ),
            ReportPageDefinition(
                code="MAP-02",
                name="地價使用分區圖",
                kind="DOCUMENT",
                document_type="map-zoning",
            ),
            ReportPageDefinition(
                code="MAP-03",
                name="地價區段圖",
                kind="DOCUMENT",
                document_type="map-land-value-section",
            ),
        ),
    )
}


def get_report_definition(report_type: str) -> ReportPackageDefinition | None:
    return REPORT_PACKAGES.get(report_type)
