from __future__ import annotations

from html import escape
from datetime import time, timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, today

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


def _period_label(from_date: str, to_date: str) -> str:
    if from_date == to_date:
        return from_date
    return f"{from_date} to {to_date}"


def _find_kpi(section: dict, label: str) -> dict | None:
    return next((kpi for kpi in section.get("kpis", []) if kpi.get("label") == label), None)


def _find_table(section: dict, title: str) -> dict | None:
    return next((table for table in section.get("tables", []) if table.get("title") == title), None)


def _kpi_value(kpi: dict | None, currency: str | None) -> str:
    if not kpi:
        return format_value(0, "Currency", currency)
    return format_value(kpi.get("value"), kpi.get("fieldtype"), currency)


def _tone_color(kpi: dict | None, risk_metric: bool = False) -> str:
    value = flt((kpi or {}).get("value") or 0)
    if risk_metric:
        return "#d92d20" if value else "#12a150"
    if value < 0:
        return "#d92d20"
    if value > 0:
        return "#12a150"
    return "#1877f2"


def _render_metric_tile(label: str, kpi: dict | None, currency: str | None, risk_metric: bool = False) -> str:
    color = _tone_color(kpi, risk_metric=risk_metric)
    return """
        <td style="width:25%;padding:6px;vertical-align:top;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #dfe3e8;border-top:4px solid {color};border-radius:8px;background:#ffffff;">
                <tr>
                    <td style="padding:12px 12px 10px;">
                        <div style="font-size:11px;line-height:14px;color:#687178;font-weight:700;text-transform:uppercase;">{label}</div>
                        <div style="font-size:20px;line-height:25px;color:#1f272e;font-weight:800;margin-top:8px;">{value}</div>
                    </td>
                </tr>
            </table>
        </td>
    """.format(
        color=color,
        label=escape(str(label)),
        value=escape(str(_kpi_value(kpi, currency))),
    )


def _render_table(table: dict, currency: str | None) -> str:
    if not table.get("rows"):
        return ""

    headers = "".join(
        f'<th style="padding:9px 8px;border-bottom:1px solid #dfe3e8;text-align:left;background:#f5f7fa;color:#687178;font-size:12px;">{escape(str(column))}</th>'
        for column in table.get("columns", [])
    )
    rows = []
    max_rows = 10 if table.get("title") in {_("Sales Person Performance Summary"), _("New Customers")} else 6
    for row in table.get("rows", [])[:max_rows]:
        cells = []
        for index, cell in enumerate(row):
            fieldtype = (table.get("fieldtypes") or [])[index] if index < len(table.get("fieldtypes") or []) else "Data"
            align = "right" if fieldtype in ("Currency", "Float", "Int", "Percent") else "left"
            cells.append(
                '<td style="padding:9px 8px;border-bottom:1px solid #eef1f4;text-align:{align};font-size:12px;line-height:16px;color:#1f272e;">{value}</td>'.format(
                    align=align,
                    value=escape(str(format_value(cell, fieldtype, currency))),
                )
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")

    return """
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #dfe3e8;border-radius:8px;background:#ffffff;margin-top:12px;">
            <tr>
                <td style="padding:12px 12px 2px;font-size:14px;line-height:18px;font-weight:800;color:#1f272e;">{title}</td>
            </tr>
            <tr>
                <td style="padding:0 12px 12px;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                        <thead><tr>{headers}</tr></thead>
                        <tbody>{rows}</tbody>
                    </table>
                </td>
            </tr>
        </table>
    """.format(
        title=escape(str(table.get("title") or "")),
        headers=headers,
        rows="\n".join(rows),
    )


def _render_signal_panel(title: str, table: dict | None, currency: str | None) -> str:
    if not table or not table.get("rows"):
        return ""

    items = []
    for row in table.get("rows", [])[:4]:
        value = format_value(row[1], (table.get("fieldtypes") or ["Data", "Currency"])[1], currency)
        note = row[2] if len(row) > 2 else ""
        items.append(
            """
            <tr>
                <td style="padding:9px 0;border-bottom:1px solid #eef1f4;">
                    <div style="font-size:13px;line-height:17px;font-weight:700;color:#1f272e;">{label}</div>
                    <div style="font-size:12px;line-height:16px;color:#687178;margin-top:2px;">{note}</div>
                </td>
                <td style="padding:9px 0 9px 10px;border-bottom:1px solid #eef1f4;text-align:right;font-size:13px;line-height:17px;font-weight:800;color:#1f272e;white-space:nowrap;">{value}</td>
            </tr>
            """.format(
                label=escape(str(row[0])),
                note=escape(str(note)),
                value=escape(str(value)),
            )
        )

    return """
        <td style="width:50%;padding:6px;vertical-align:top;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #dfe3e8;border-radius:8px;background:#ffffff;">
                <tr>
                    <td style="padding:12px 12px 4px;font-size:14px;line-height:18px;font-weight:800;color:#1f272e;">{title}</td>
                </tr>
                <tr>
                    <td style="padding:0 12px 10px;">
                        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">{items}</table>
                    </td>
                </tr>
            </table>
        </td>
    """.format(title=escape(str(title)), items="\n".join(items))


def _render_bar_chart(title: str, chart: dict | None, currency: str | None) -> str:
    if not chart or not chart.get("points"):
        return ""

    points = chart.get("points", [])[:8]
    max_value = max(abs(flt(point.get("value") or 0)) for point in points) or 1
    rows = []
    for point in points:
        value = flt(point.get("value") or 0)
        width = max(4, min(100, abs(value) / max_value * 100))
        color = "#d92d20" if value < 0 else "#1877f2"
        rows.append(
            """
            <tr>
                <td style="width:32%;padding:6px 8px 6px 0;font-size:12px;line-height:15px;color:#1f272e;font-weight:700;vertical-align:middle;">{label}</td>
                <td style="width:48%;padding:6px 8px 6px 0;vertical-align:middle;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#edf2f7;border-radius:999px;">
                        <tr>
                            <td style="width:{width:.0f}%;height:10px;background:{color};border-radius:999px;font-size:0;line-height:0;">&nbsp;</td>
                            <td style="font-size:0;line-height:0;">&nbsp;</td>
                        </tr>
                    </table>
                </td>
                <td style="width:20%;padding:6px 0;font-size:12px;line-height:15px;color:#687178;text-align:right;white-space:nowrap;vertical-align:middle;">{value}</td>
            </tr>
            """.format(
                label=escape(str(point.get("label") or "")),
                width=width,
                color=color,
                value=escape(str(format_value(value, chart.get("fieldtype") or "Currency", currency))),
            )
        )

    return """
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #dfe3e8;border-radius:8px;background:#ffffff;margin-top:12px;">
            <tr>
                <td style="padding:12px 12px 2px;font-size:14px;line-height:18px;font-weight:800;color:#1f272e;">{title}</td>
            </tr>
            <tr>
                <td style="padding:4px 12px 12px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>
                </td>
            </tr>
        </table>
    """.format(title=escape(str(title)), rows="\n".join(rows))


def _render_chart_grid(overview: dict, currency: str | None) -> str:
    charts = overview.get("charts") or []
    chart_map = {chart.get("title"): chart for chart in charts}
    chart_html = "\n".join(
        filter(
            None,
            [
                _render_bar_chart(_("Daily Sales Performance"), chart_map.get(_("Daily Sales Performance")), currency),
                _render_bar_chart(_("Sales Person Performance"), chart_map.get(_("Sales Person Performance")), currency),
            ],
        )
    )
    if not chart_html:
        return ""

    return """
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td style="width:50%;padding:0 6px 0 0;vertical-align:top;">{left_chart}</td>
                <td style="width:50%;padding:0 0 0 6px;vertical-align:top;">{right_chart}</td>
            </tr>
        </table>
    """.format(
        left_chart=_render_bar_chart(_("Daily Sales Performance"), chart_map.get(_("Daily Sales Performance")), currency),
        right_chart=_render_bar_chart(_("Sales Person Performance"), chart_map.get(_("Sales Person Performance")), currency),
    )


def _render_executive_overview_html(dashboard: dict, dashboard_url: str) -> str:
    currency = dashboard.get("currency")
    overview = dashboard.get("tabs", {}).get("overview", {})

    metric_html = "".join(
        [
            _render_metric_tile(_("Net Sales"), _find_kpi(overview, _("Net Sales")), currency),
            _render_metric_tile(_("Gross Profit"), _find_kpi(overview, _("Gross Profit")), currency),
            _render_metric_tile(_("Cash Balance"), _find_kpi(overview, _("Cash and Bank Balance")), currency),
            _render_metric_tile(_("Overdue Receivables"), _find_kpi(overview, _("Overdue Receivables")), currency, risk_metric=True),
        ]
    )
    secondary_metric_html = "".join(
        [
            _render_metric_tile(_("Expense"), _find_kpi(overview, _("Expense")), currency, risk_metric=True),
            _render_metric_tile(_("Outstanding Sales"), _find_kpi(overview, _("Outstanding Sales")), currency, risk_metric=True),
            _render_metric_tile(_("Payables Due Soon"), _find_kpi(overview, _("Payables Due Soon")), currency, risk_metric=True),
            _render_metric_tile(_("New Customers"), _find_kpi(overview, _("New Customers")), currency),
        ]
    )
    signal_html = "\n".join(
        filter(
            None,
            [
                _render_signal_panel(_("Executive Risks"), _find_table(overview, _("Executive Risks")), currency),
                _render_signal_panel(_("Sales Opportunities"), _find_table(overview, _("Sales Opportunities")), currency),
            ],
        )
    )
    chart_html = _render_chart_grid(overview, currency)
    table_html = "\n".join(
        filter(
            None,
            [
                _render_table(_find_table(overview, _("Daily Sales Performance")) or {}, currency),
                _render_table(_find_table(overview, _("Sales Person Performance Summary")) or {}, currency),
                _render_table(_find_table(overview, _("New Customers")) or {}, currency),
                _render_table(_find_table(overview, _("Sales Person Performance")) or {}, currency),
                _render_table(_find_table(overview, _("Top Receivables Risks")) or {}, currency),
                _render_table(_find_table(overview, _("Upcoming Payables Pressure")) or {}, currency),
            ],
        )
    )

    return """
        <div style="margin:0;padding:0;background:#f5f7fa;font-family:Arial, sans-serif;color:#1f272e;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f7fa;">
                <tr>
                    <td align="center" style="padding:18px 10px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:960px;background:#ffffff;border:1px solid #dfe3e8;border-radius:8px;">
                            <tr>
                                <td style="padding:22px 22px 16px;background:#102a43;border-radius:8px 8px 0 0;">
                                    <div style="font-size:11px;line-height:14px;color:#9fb3c8;font-weight:800;text-transform:uppercase;">{eyebrow}</div>
                                    <div style="font-size:24px;line-height:30px;color:#ffffff;font-weight:800;margin-top:5px;">{title}</div>
                                    <div style="font-size:13px;line-height:18px;color:#d9e2ec;margin-top:6px;">{period_label}: <strong>{period}</strong></div>
                                </td>
                            </tr>
                            <tr><td style="padding:14px 16px 4px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{metric_html}</tr></table></td></tr>
                            <tr><td style="padding:0 16px 8px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{secondary_metric_html}</tr></table></td></tr>
                            <tr><td style="padding:0 16px 6px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{signal_html}</tr></table></td></tr>
                            <tr><td style="padding:0 22px 8px;">{chart_html}</td></tr>
                            <tr><td style="padding:0 22px 8px;">{table_html}</td></tr>
                            <tr>
                                <td style="padding:8px 22px 22px;">
                                    <a href="{dashboard_url}" style="background:#1877f2;color:#ffffff;padding:11px 15px;text-decoration:none;border-radius:4px;display:inline-block;font-size:13px;font-weight:700;">{dashboard_link_label}</a>
                                    <div style="color:#687178;font-size:12px;line-height:16px;margin-top:12px;">{attachment_note}</div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </div>
    """.format(
        eyebrow=_("Executive Report"),
        title=_("Daily Executive Dashboard"),
        period_label=_("Report Date"),
        period=escape(_period_label(str(dashboard.get("from_date") or ""), str(dashboard.get("to_date") or ""))),
        metric_html=metric_html,
        secondary_metric_html=secondary_metric_html,
        signal_html=signal_html,
        chart_html=chart_html,
        table_html=table_html,
        dashboard_url=escape(dashboard_url, quote=True),
        dashboard_link_label=_("Open Live Dashboard"),
        attachment_note=_("This email is an inline dashboard summary. Use the live dashboard for filters, drill-downs, and simulations."),
    )


def _send_summary(
    ignore_schedule: bool = False,
    mark_sent: bool = True,
    from_date: str | None = None,
    to_date: str | None = None,
) -> None:
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

    if from_date or to_date:
        to_date = str(getdate(to_date or from_date))
        from_date = str(getdate(from_date or to_date))
        if getdate(from_date) > getdate(to_date):
            frappe.throw(_("From Date cannot be after To Date."))
    else:
        from_date, to_date = _today_range()

    dashboard = get_dashboard_for_email(from_date=from_date, to_date=to_date)
    message = _render_executive_overview_html(dashboard, _dashboard_url(from_date, to_date))
    period = _period_label(from_date, to_date)

    frappe.sendmail(
        recipients=recipients,
        subject=f"{settings.email_subject or _('Daily Executive Performance Summary')} - {period}",
        message=message,
        reference_doctype="Executive Report Settings",
        reference_name="Executive Report Settings",
    )

    if mark_sent:
        frappe.db.set_single_value("Executive Report Settings", "last_sent_date", to_date)


def send_daily_summary() -> None:
    _send_summary()


@frappe.whitelist()
def send_summary_now(from_date: str | None = None, to_date: str | None = None) -> None:
    require_executive_report_manager()
    _send_summary(ignore_schedule=True, mark_sent=False, from_date=from_date, to_date=to_date)
