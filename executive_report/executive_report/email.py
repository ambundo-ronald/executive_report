from __future__ import annotations

from html import escape
from datetime import time, timedelta

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today

from executive_report.executive_report.api import (
    format_value,
    get_enabled_recipients,
    get_dashboard_for_email,
)
from executive_report.executive_report.permissions import require_executive_report_manager


def _today_range() -> tuple[str, str]:
    report_date = str(getdate(today()))
    return report_date, report_date


def _seconds_since_midnight(value) -> int:
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    if isinstance(value, time):
        return value.hour * 3600 + value.minute * 60 + value.second

    parts = str(value or "00:00:00").split(":")
    hours = int(parts[0]) if len(parts) > 0 and parts[0] else 0
    minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    seconds = int(float(parts[2])) if len(parts) > 2 and parts[2] else 0
    return hours * 3600 + minutes * 60 + seconds


def _should_send_now(settings) -> bool:
    current_date = str(getdate(today()))
    if str(settings.last_sent_date or "") == current_date:
        return False

    return _seconds_since_midnight(now_datetime().time()) >= _seconds_since_midnight(settings.send_time)


def _dashboard_url(from_date: str, to_date: str) -> str:
    return frappe.utils.get_url(f"/app/executive-dashboard?from_date={from_date}&to_date={to_date}")


def _render_table(table: dict, currency: str | None) -> str:
    if not table.get("rows"):
        return ""

    headers = "".join(
        f'<th style="padding:8px;border:1px solid #dfe3e8;text-align:left;background:#f5f7fa;">{escape(str(column))}</th>'
        for column in table.get("columns", [])
    )
    rows = []
    for row in table.get("rows", [])[:10]:
        cells = []
        for index, cell in enumerate(row):
            fieldtype = (table.get("fieldtypes") or [])[index] if index < len(table.get("fieldtypes") or []) else "Data"
            align = "right" if fieldtype in ("Currency", "Float", "Int", "Percent") else "left"
            cells.append(
                '<td style="padding:8px;border:1px solid #dfe3e8;text-align:{align};">{value}</td>'.format(
                    align=align,
                    value=escape(str(format_value(cell, fieldtype, currency))),
                )
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")

    return """
        <h3 style="font-size:15px;margin:22px 0 8px;">{title}</h3>
        <table style="border-collapse:collapse;width:100%;max-width:920px;">
            <thead><tr>{headers}</tr></thead>
            <tbody>{rows}</tbody>
        </table>
    """.format(
        title=escape(str(table.get("title") or "")),
        headers=headers,
        rows="\n".join(rows),
    )


def _render_executive_overview_html(dashboard: dict, dashboard_url: str) -> str:
    currency = dashboard.get("currency")
    overview = dashboard.get("tabs", {}).get("overview", {})
    expense_kpi = next(
        (kpi for kpi in overview.get("kpis", []) if kpi.get("label") == _("Expense")),
        None,
    )
    expense_summary = ""
    if expense_kpi:
        expense_summary = """
            <p style="margin:0 0 16px;font-size:15px;">
                {label}: <strong>{value}</strong>
            </p>
        """.format(
            label=_("This is how much we have spent today"),
            value=escape(str(format_value(expense_kpi.get("value"), expense_kpi.get("fieldtype"), currency))),
        )

    kpi_rows = []
    for kpi in overview.get("kpis", []):
        kpi_rows.append(
            """
            <tr>
                <td style="padding:8px;border:1px solid #dfe3e8;">{label}</td>
                <td style="padding:8px;border:1px solid #dfe3e8;text-align:right;">{value}</td>
            </tr>
            """.format(
                label=escape(str(kpi.get("label") or "")),
                value=escape(str(format_value(kpi.get("value"), kpi.get("fieldtype"), currency))),
            )
        )

    if not kpi_rows:
        kpi_rows.append(
            """
            <tr><td colspan="2" style="padding:8px;border:1px solid #dfe3e8;">No executive overview data found.</td></tr>
            """
        )

    selected_tables = {
        _("Daily Sales Performance"),
        _("Sales Person Performance"),
        _("Outstanding by Sales Person"),
        _("Top Receivables Risks"),
        _("Upcoming Payables Pressure"),
        _("Executive Risks"),
        _("Sales Opportunities"),
    }
    table_html = "\n".join(
        _render_table(table, currency)
        for table in overview.get("tables", [])
        if table.get("title") in selected_tables
    )

    return """
        <div style="font-family:Arial, sans-serif;color:#1f272e;">
            <h2 style="font-size:20px;margin:0 0 8px;">{title}</h2>
            <p style="margin:0 0 16px;">{period_label}: <strong>{from_date}</strong></p>
            {expense_summary}
            <table style="border-collapse:collapse;width:100%;max-width:760px;">
                <thead>
                    <tr>
                        <th style="padding:8px;border:1px solid #dfe3e8;text-align:left;background:#f5f7fa;">{metric_label}</th>
                        <th style="padding:8px;border:1px solid #dfe3e8;text-align:right;background:#f5f7fa;">{value_label}</th>
                    </tr>
                </thead>
                <tbody>{kpi_rows}</tbody>
            </table>
            {table_html}
            <p style="margin-top:22px;">
                <a href="{dashboard_url}" style="background:#1877f2;color:#ffffff;padding:10px 14px;text-decoration:none;border-radius:4px;display:inline-block;">
                    {dashboard_link_label}
                </a>
            </p>
            <p style="color:#687178;font-size:12px;margin-top:16px;">{attachment_note}</p>
        </div>
    """.format(
        title=_("Daily Executive Overview"),
        period_label=_("Report Date"),
        from_date=escape(str(dashboard.get("from_date") or "")),
        expense_summary=expense_summary,
        metric_label=_("Metric"),
        value_label=_("Value"),
        kpi_rows="\n".join(kpi_rows),
        table_html=table_html,
        dashboard_url=escape(dashboard_url, quote=True),
        dashboard_link_label=_("Open Executive Dashboard"),
        attachment_note=_("No attachment is included. This email is an inline daily Executive Overview summary."),
    )


def _send_summary(ignore_schedule: bool = False, mark_sent: bool = True) -> None:
    if not frappe.db.exists("DocType", "Executive Report Settings"):
        return

    settings = frappe.get_single("Executive Report Settings")
    if not settings.enabled:
        return
    if not ignore_schedule and not _should_send_now(settings):
        return

    recipients = get_enabled_recipients()
    if not recipients:
        return

    from_date, to_date = _today_range()
    dashboard = get_dashboard_for_email(from_date=from_date, to_date=to_date)
    message = _render_executive_overview_html(dashboard, _dashboard_url(from_date, to_date))

    frappe.sendmail(
        recipients=recipients,
        subject=f"{settings.email_subject or _('Daily Executive Performance Summary')} - {to_date}",
        message=message,
        reference_doctype="Executive Report Settings",
        reference_name="Executive Report Settings",
    )

    if mark_sent:
        frappe.db.set_single_value("Executive Report Settings", "last_sent_date", to_date)


def send_daily_summary() -> None:
    _send_summary()


@frappe.whitelist()
def send_summary_now() -> None:
    require_executive_report_manager()
    _send_summary(ignore_schedule=True, mark_sent=False)
