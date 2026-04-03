from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..models import ErrorReport
from ._paths import StoragePaths


class ErrorReportStorage:
    def __init__(self, paths: StoragePaths) -> None:
        self._paths = paths

    def write_error_report(self, report: ErrorReport) -> ErrorReport:
        now = datetime.now()
        if report.created_at:
            created_at = report.created_at
            stamp = self._report_filename_stamp(report.created_at, fallback=now)
        else:
            created_at = now.isoformat(timespec="seconds")
            stamp = now.strftime("%Y%m%d-%H%M%S")
        report.created_at = created_at
        report_path = self._unique_report_path(stamp)
        report.report_path = str(report_path)
        content = self._format_error_report(report)
        report_path.write_text(content, encoding="utf-8")
        (self._paths.reports_dir / "latest-error.txt").write_text(content, encoding="utf-8")
        return report

    def _unique_report_path(self, stamp: str) -> Path:
        candidate = self._paths.reports_dir / f"error-report-{stamp}.txt"
        if not candidate.exists():
            return candidate
        index = 1
        while True:
            candidate = self._paths.reports_dir / f"error-report-{stamp}-{index}.txt"
            if not candidate.exists():
                return candidate
            index += 1

    def _report_filename_stamp(self, created_at: str, *, fallback: datetime) -> str:
        try:
            parsed = datetime.fromisoformat(created_at)
        except ValueError:
            parsed = fallback
        return parsed.strftime("%Y%m%d-%H%M%S")

    def _format_error_report(self, report: ErrorReport) -> str:
        lines = [
            "HainTag Error Report",
            f"Time: {report.created_at}",
            f"Kind: {report.kind}",
        ]
        run_mode = str(report.context.get("run_mode", "") or "")
        if run_mode:
            lines.append(f"Run Mode: {run_mode}")
        lines.append(f"Summary: {report.summary or '(empty)'}")
        lines.append(f"Report Path: {report.report_path or '(pending)'}")
        context_items = [(key, value) for key, value in report.context.items() if key != "run_mode"]
        if context_items:
            lines.append("")
            lines.append("Context:")
            for key, value in context_items:
                lines.append(f"- {key}: {value}")
        if report.details:
            lines.append("")
            lines.append("Details:")
            lines.append(report.details.rstrip())
        return "\n".join(lines).rstrip() + "\n"

