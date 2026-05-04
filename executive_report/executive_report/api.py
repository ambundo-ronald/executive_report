from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from executive_report.executive_report.permissions import require_executive_report_access


def _default_dates(from_date: str | None, to_date: str | None) -> tuple[str, str]:
    end = getdate(to_date or today())
    start = getdate(from_date) if from_date else add_days(end, -29)
    return str(start), str(end)


def _doctype_exists(doctype: str) -> bool:
    return bool(frappe.db.exists("DocType", doctype))


def _has_column(doctype: str, fieldname: str) -> bool:
    return _doctype_exists(doctype) and bool(frappe.db.has_column(doctype, fieldname))


def _get_company_currency() -> str | None:
    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )
    if not company or not _doctype_exists("Company"):
        return None
    return frappe.db.get_value("Company", company, "default_currency")


def _sum(sql: str, values: dict) -> float:
    result = frappe.db.sql(sql, values, as_dict=True)
    if not result:
        return 0
    return flt(result[0].get("value"))


def _rows(sql: str, values: dict) -> list[dict]:
    return frappe.db.sql(sql, values, as_dict=True)


def _list_route(doctype: str, filters: dict | None = None) -> dict:
    return {"type": "List", "doctype": doctype, "filters": filters or {}}


def _report_route(report_name: str, filters: dict | None = None) -> dict:
    return {"type": "Report", "report_name": report_name, "filters": filters or {}}


def _period_filter(fieldname: str, from_date: str, to_date: str) -> dict:
    return {fieldname: ["between", [from_date, to_date]]}


def _number_card(label: str, value, fieldtype: str = "Float", route: dict | None = None) -> dict:
    card = {"label": label, "value": value, "fieldtype": fieldtype}
    if route:
        card["route"] = route
    return card


def _date_columns(from_date: str, to_date: str) -> list[str]:
    start = getdate(from_date)
    end = getdate(to_date)
    dates = []
    current = start
    while current <= end:
        dates.append(str(current))
        current = add_days(current, 1)
    return dates


def _month_start(value) -> date:
    value = getdate(value)
    return date(value.year, value.month, 1)


def _add_months(value, months: int) -> date:
    value = getdate(value)
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _month_key(value) -> str:
    value = getdate(value)
    return f"{value.year:04d}-{value.month:02d}"


def _month_label(value) -> str:
    value = getdate(value)
    return value.strftime("%b %Y")


def _sales(from_date: str, to_date: str) -> dict:
    if not _doctype_exists("Sales Invoice"):
        return {"kpis": [], "tables": [], "notes": [_("Sales Invoice is not installed.")]}

    values = {"from_date": from_date, "to_date": to_date}
    notes = []
    total_sales = _sum(
        """
        select sum(base_net_total) as value
        from `tabSales Invoice`
        where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
        """,
        values,
    )
    invoices = _sum(
        """
        select count(*) as value
        from `tabSales Invoice`
        where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
        """,
        values,
    )
    outstanding = _sum(
        """
        select sum(outstanding_amount) as value
        from `tabSales Invoice`
        where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
        """,
        values,
    )
    top_customers = _rows(
        """
        select customer as label, sum(base_net_total) as amount, count(*) as count
        from `tabSales Invoice`
        where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
        group by customer
        order by amount desc
        limit 10
        """,
        values,
    )
    sales_by_person = []
    outstanding_by_person = []
    heatmap_rows = []
    if _doctype_exists("Sales Team"):
        sales_by_person = _rows(
            """
            select
                st.sales_person as label,
                sum(coalesce(st.allocated_amount, si.base_net_total * st.allocated_percentage / 100)) as amount,
                count(distinct si.name) as count
            from `tabSales Invoice` si
            inner join `tabSales Team` st
                on st.parent = si.name and st.parenttype = 'Sales Invoice'
            where si.docstatus = 1
              and si.posting_date between %(from_date)s and %(to_date)s
              and st.sales_person is not null
              and st.sales_person != ''
            group by st.sales_person
            order by amount desc
            limit 10
            """,
            values,
        )
        outstanding_by_person = _rows(
            """
            select
                st.sales_person as label,
                sum(si.outstanding_amount * coalesce(st.allocated_percentage, 100) / 100) as amount,
                count(distinct si.name) as count
            from `tabSales Invoice` si
            inner join `tabSales Team` st
                on st.parent = si.name and st.parenttype = 'Sales Invoice'
            where si.docstatus = 1
              and si.posting_date between %(from_date)s and %(to_date)s
              and si.outstanding_amount != 0
              and st.sales_person is not null
              and st.sales_person != ''
            group by st.sales_person
            having amount != 0
            order by amount desc
            limit 10
            """,
            values,
        )
        heatmap_data = _rows(
            """
            select
                st.sales_person as sales_person,
                si.posting_date as posting_date,
                sum(coalesce(st.allocated_amount, si.base_net_total * st.allocated_percentage / 100)) as amount
            from `tabSales Invoice` si
            inner join `tabSales Team` st
                on st.parent = si.name and st.parenttype = 'Sales Invoice'
            where si.docstatus = 1
              and si.posting_date between %(from_date)s and %(to_date)s
              and st.sales_person is not null
              and st.sales_person != ''
            group by st.sales_person, si.posting_date
            order by st.sales_person, si.posting_date
            """,
            values,
        )
        dates = _date_columns(from_date, to_date)
        amounts_by_person = {}
        for row in heatmap_data:
            person = row.sales_person
            amounts_by_person.setdefault(person, {date: 0 for date in dates})
            amounts_by_person[person][str(row.posting_date)] = flt(row.amount)

        heatmap_rows = [
            {
                "label": person,
                "values": [daily_amounts[date] for date in dates],
                "total": sum(daily_amounts.values()),
            }
            for person, daily_amounts in amounts_by_person.items()
        ]
        heatmap_rows.sort(key=lambda row: row["total"], reverse=True)
    else:
        notes.append(_("Sales Team is not available, so sales person performance is hidden."))

    return {
        "kpis": [
            _number_card(_("Net Sales"), total_sales, "Currency", _list_route("Sales Invoice", {"docstatus": 1, **_period_filter("posting_date", from_date, to_date)})),
            _number_card(_("Sales Invoices"), invoices, "Int", _list_route("Sales Invoice", {"docstatus": 1, **_period_filter("posting_date", from_date, to_date)})),
            _number_card(_("Average Invoice"), total_sales / invoices if invoices else 0, "Currency"),
            _number_card(_("Outstanding"), outstanding, "Currency", _report_route("Accounts Receivable", {"report_date": to_date})),
        ],
        "tables": [
            {
                "title": _("Top Customers"),
                "columns": [_("Customer"), _("Sales"), _("Invoices")],
                "rows": [[row.label, row.amount, row.count] for row in top_customers],
                "fieldtypes": ["Data", "Currency", "Int"],
                "row_routes": [
                    _list_route("Sales Invoice", {"docstatus": 1, "customer": row.label, **_period_filter("posting_date", from_date, to_date)})
                    for row in top_customers
                ],
            },
            {
                "title": _("Sales Performance by Sales Person"),
                "columns": [_("Sales Person"), _("Allocated Sales"), _("Invoices")],
                "rows": [[row.label, row.amount, row.count] for row in sales_by_person],
                "fieldtypes": ["Data", "Currency", "Int"],
            },
            {
                "title": _("Outstanding by Sales Person"),
                "columns": [_("Sales Person"), _("Allocated Outstanding"), _("Invoices")],
                "rows": [[row.label, row.amount, row.count] for row in outstanding_by_person],
                "fieldtypes": ["Data", "Currency", "Int"],
            }
        ],
        "heatmaps": [
            {
                "title": _("Sales Person Heatmap"),
                "columns": _date_columns(from_date, to_date),
                "rows": heatmap_rows[:15],
                "fieldtype": "Currency",
            }
        ],
        "notes": notes,
    }


def _get_sales_person_user_rows() -> list[dict]:
    if not (_doctype_exists("Sales Person") and _doctype_exists("Employee")):
        return []
    if not (_has_column("Sales Person", "employee") and _has_column("Employee", "user_id")):
        return []

    enabled_filter = "and coalesce(sp.enabled, 1) = 1" if _has_column("Sales Person", "enabled") else ""
    return _rows(
        f"""
        select sp.name as sales_person, employee.user_id as user
        from `tabSales Person` sp
        inner join `tabEmployee` employee on employee.name = sp.employee
        where employee.user_id is not null
          and employee.user_id != ''
          {enabled_filter}
        """,
        {},
    )


def _sales_person_usage(from_date: str, to_date: str) -> tuple[list[dict], list[dict], list[str]]:
    notes = []
    if not _doctype_exists("Activity Log"):
        return [], [], [_("Activity Log is not available.")]

    sales_person_users = _get_sales_person_user_rows()
    if not sales_person_users:
        return [], [], [_("Sales Person records are not linked to Employee user IDs.")]

    dates = _date_columns(from_date, to_date)
    users = tuple(row.user for row in sales_person_users)
    user_to_sales_person = {row.user: row.sales_person for row in sales_person_users}

    usage_data = _rows(
        """
        select user, date(creation) as activity_date, count(*) as count
        from `tabActivity Log`
        where date(creation) between %(from_date)s and %(to_date)s
          and user in %(users)s
        group by user, date(creation)
        order by user, activity_date
        """,
        {"from_date": from_date, "to_date": to_date, "users": users},
    )

    counts_by_person = {}
    for row in usage_data:
        person = user_to_sales_person.get(row.user)
        if not person:
            continue
        counts_by_person.setdefault(person, {date: 0 for date in dates})
        counts_by_person[person][str(row.activity_date)] = flt(row.count)

    heatmap_rows = [
        {
            "label": person,
            "values": [daily_counts[date] for date in dates],
            "total": sum(daily_counts.values()),
        }
        for person, daily_counts in counts_by_person.items()
    ]
    heatmap_rows.sort(key=lambda row: row["total"], reverse=True)

    if _has_column("Activity Log", "reference_doctype") and _has_column("Activity Log", "operation"):
        system_area_expression = "coalesce(nullif(activity.reference_doctype, ''), activity.operation, 'Unknown')"
    elif _has_column("Activity Log", "reference_doctype"):
        system_area_expression = "coalesce(nullif(activity.reference_doctype, ''), 'Unknown')"
    elif _has_column("Activity Log", "operation"):
        system_area_expression = "coalesce(nullif(activity.operation, ''), 'Unknown')"
    else:
        system_area_expression = "'Activity Log'"

    area_rows = _rows(
        f"""
        select
            activity.user,
            {system_area_expression} as system_area,
            count(*) as count
        from `tabActivity Log` activity
        where date(activity.creation) between %(from_date)s and %(to_date)s
          and activity.user in %(users)s
        group by activity.user, system_area
        order by count desc
        limit 30
        """,
        {"from_date": from_date, "to_date": to_date, "users": users},
    )
    interaction_rows = [
        {
            "sales_person": user_to_sales_person.get(row.user, row.user),
            "system_area": row.system_area,
            "count": row.count,
        }
        for row in area_rows
    ]

    return heatmap_rows[:15], interaction_rows, notes


def _previous_period(from_date: str, to_date: str) -> tuple[str, str]:
    start = getdate(from_date)
    end = getdate(to_date)
    days = (end - start).days + 1
    previous_to = add_days(start, -1)
    previous_from = add_days(previous_to, -(days - 1))
    return str(previous_from), str(previous_to)


def _change_percent(current: float, previous: float) -> float:
    if not previous:
        return 100 if current else 0
    return (current - previous) / previous * 100


def _cash_balance(to_date: str) -> float:
    if not (_doctype_exists("GL Entry") and _doctype_exists("Account")):
        return 0

    return _sum(
        """
        select sum(gle.debit - gle.credit) as value
        from `tabGL Entry` gle
        inner join `tabAccount` account on account.name = gle.account
        where gle.docstatus = 1
          and account.account_type in ('Bank', 'Cash')
          and gle.posting_date <= %(to_date)s
        """,
        {"to_date": to_date},
    )


def _fiscal_year_dates(reference_date: str) -> tuple[str, str]:
    reference = getdate(reference_date)
    if _doctype_exists("Fiscal Year"):
        fiscal_year = frappe.db.sql(
            """
            select year_start_date, year_end_date
            from `tabFiscal Year`
            where year_start_date <= %(reference_date)s
              and year_end_date >= %(reference_date)s
              and disabled = 0
            order by year_start_date desc
            limit 1
            """,
            {"reference_date": reference},
            as_dict=True,
        )
        if fiscal_year:
            return str(fiscal_year[0].year_start_date), str(fiscal_year[0].year_end_date)

    return str(date(reference.year, 1, 1)), str(date(reference.year, 12, 31))


def _monthly_pnl_rows(from_date: str, to_date: str) -> list[dict]:
    if not (_doctype_exists("GL Entry") and _doctype_exists("Account")):
        return []

    return _rows(
        """
        select date_format(gle.posting_date, '%%Y-%%m') as month,
               sum(case when account.root_type = 'Income' then gle.credit - gle.debit else 0 end) as revenue,
               sum(case when account.root_type = 'Expense' then gle.debit - gle.credit else 0 end) as expense
        from `tabGL Entry` gle
        inner join `tabAccount` account on account.name = gle.account
        where gle.docstatus = 1
          and account.root_type in ('Income', 'Expense')
          and gle.posting_date between %(from_date)s and %(to_date)s
        group by date_format(gle.posting_date, '%%Y-%%m')
        order by month
        """,
        {"from_date": from_date, "to_date": to_date},
    )


def _projection_and_simulation(
    to_date: str | None = None,
    revenue_growth_percent: float = 0,
    expense_growth_percent: float = 0,
    collection_rate_percent: float = 75,
    one_time_revenue: float = 0,
    one_time_expense: float = 0,
    profit_target: float = 0,
    minimum_cash_balance: float = 0,
) -> dict:
    reference_date = str(getdate(to_date or today()))
    fiscal_start, fiscal_end = _fiscal_year_dates(reference_date)
    actual_rows = _monthly_pnl_rows(fiscal_start, reference_date)
    actual_by_month = {
        row.month: {
            "revenue": flt(row.revenue),
            "expense": flt(row.expense),
            "net_profit": flt(row.revenue) - flt(row.expense),
        }
        for row in actual_rows
    }

    actual_months = max(len(actual_by_month), 1)
    actual_revenue = sum(row["revenue"] for row in actual_by_month.values())
    actual_expense = sum(row["expense"] for row in actual_by_month.values())
    average_revenue = actual_revenue / actual_months
    average_expense = actual_expense / actual_months

    first_projection_month = _month_start(_add_months(reference_date, 1))
    end_month = _month_start(fiscal_end)

    def build_projection_rows(revenue_growth, expense_growth, collection_rate, extra_revenue=0, extra_expense=0):
        rows = []
        current_month = _month_start(fiscal_start)
        one_time_applied = False
        opening_cash = cash_balance

        while current_month <= end_month:
            key = _month_key(current_month)
            if key in actual_by_month:
                revenue = actual_by_month[key]["revenue"]
                expense = actual_by_month[key]["expense"]
                collected = revenue
                row_type = _("Actual")
            elif current_month >= first_projection_month:
                months_ahead = max(
                    (current_month.year - first_projection_month.year) * 12
                    + current_month.month
                    - first_projection_month.month,
                    0,
                )
                revenue = average_revenue * ((1 + flt(revenue_growth) / 100) ** (months_ahead + 1))
                expense = average_expense * ((1 + flt(expense_growth) / 100) ** (months_ahead + 1))
                if not one_time_applied:
                    revenue += flt(extra_revenue)
                    expense += flt(extra_expense)
                    one_time_applied = True
                collected = revenue * flt(collection_rate) / 100
                row_type = _("Projected")
            else:
                revenue = 0
                expense = 0
                collected = 0
                row_type = _("Open")

            net_cash_flow = collected - expense
            if row_type == _("Projected"):
                opening_cash = opening_cash + net_cash_flow
            rows.append(
                {
                    "month": _month_label(current_month),
                    "revenue": revenue,
                    "expense": expense,
                    "collections": collected,
                    "net_cash_flow": net_cash_flow,
                    "closing_cash": opening_cash,
                    "net_profit": revenue - expense,
                    "type": row_type,
                }
            )
            current_month = _month_start(_add_months(current_month, 1))
        return rows

    cash_balance = _cash_balance(reference_date)
    projected_rows = build_projection_rows(
        revenue_growth_percent,
        expense_growth_percent,
        collection_rate_percent,
        one_time_revenue,
        one_time_expense,
    )

    projected_revenue = sum(row["revenue"] for row in projected_rows)
    projected_expense = sum(row["expense"] for row in projected_rows)
    projected_profit = projected_revenue - projected_expense
    projected_margin = (projected_profit / projected_revenue * 100) if projected_revenue else 0
    estimated_collections = projected_revenue * flt(collection_rate_percent) / 100
    expense_ratio = (projected_expense / projected_revenue * 100) if projected_revenue else 0
    projected_months = len([row for row in projected_rows if row["type"] == _("Projected")])
    remaining_profit = sum(row["net_profit"] for row in projected_rows if row["type"] == _("Projected"))
    break_even_revenue = average_expense
    required_daily_sales = break_even_revenue / 30 if break_even_revenue else 0
    required_profit_gap = max(flt(profit_target) - projected_profit, 0)
    required_monthly_revenue = (required_profit_gap / projected_months) + average_revenue if projected_months else 0
    required_expense_reduction = required_profit_gap / projected_months if projected_months else 0
    minimum_projected_cash = min([row["closing_cash"] for row in projected_rows] or [cash_balance])

    health_score = 50
    health_score += min(max(projected_margin, -20), 30)
    health_score += 15 if cash_balance > average_expense else -10
    health_score += 10 if flt(collection_rate_percent) >= 80 else -10
    health_score -= 10 if expense_ratio > 85 else 0
    health_score = max(0, min(100, health_score))

    recommendations = []
    if projected_margin < 10:
        recommendations.append([_("Margin Pressure"), _("Review pricing, discounts, and high-cost expense accounts.")])
    if expense_ratio > 85:
        recommendations.append([_("Expense Control"), _("Expenses are consuming most projected revenue; set cost ceilings by department.")])
    if flt(collection_rate_percent) < 75:
        recommendations.append([_("Collections Risk"), _("Projected cash depends on better collections; prioritize overdue receivables.")])
    if cash_balance < average_expense:
        recommendations.append([_("Liquidity Watch"), _("Cash and bank balance is below one average month of expenses.")])
    if flt(minimum_cash_balance) and minimum_projected_cash < flt(minimum_cash_balance):
        recommendations.append([_("Cash Floor Risk"), _("Projected cash falls below the minimum cash balance set in the simulation.")])
    if flt(profit_target) and projected_profit < flt(profit_target):
        recommendations.append([_("Profit Target Gap"), _("Projected fiscal-year profit is below the target; review required revenue and expense actions.")])
    if not recommendations:
        recommendations.append([_("Stable Outlook"), _("Current run-rate supports the projected fiscal-year position.")])

    scenario_inputs = [
        (_("Base Case"), revenue_growth_percent, expense_growth_percent, collection_rate_percent),
        (_("Optimistic Case"), flt(revenue_growth_percent) + 5, max(flt(expense_growth_percent) - 2, -100), min(flt(collection_rate_percent) + 10, 100)),
        (_("Conservative Case"), flt(revenue_growth_percent) - 5, flt(expense_growth_percent) + 3, max(flt(collection_rate_percent) - 10, 0)),
        (_("Stress Case"), flt(revenue_growth_percent) - 12, flt(expense_growth_percent) + 8, max(flt(collection_rate_percent) - 20, 0)),
    ]
    scenario_rows = []
    sensitivity_rows = []
    base_profit = projected_profit
    for label, revenue_growth, expense_growth, collection_rate in scenario_inputs:
        rows = build_projection_rows(revenue_growth, expense_growth, collection_rate, one_time_revenue, one_time_expense)
        scenario_revenue = sum(row["revenue"] for row in rows)
        scenario_expense = sum(row["expense"] for row in rows)
        scenario_profit = scenario_revenue - scenario_expense
        scenario_cash = min([row["closing_cash"] for row in rows] or [cash_balance])
        scenario_rows.append(
            [
                label,
                scenario_revenue,
                scenario_expense,
                scenario_profit,
                (scenario_profit / scenario_revenue * 100) if scenario_revenue else 0,
                scenario_cash,
            ]
        )

    sensitivity_tests = [
        (_("Revenue Growth +5%"), flt(revenue_growth_percent) + 5, expense_growth_percent, collection_rate_percent),
        (_("Expense Growth +5%"), revenue_growth_percent, flt(expense_growth_percent) + 5, collection_rate_percent),
        (_("Collection Rate -10%"), revenue_growth_percent, expense_growth_percent, max(flt(collection_rate_percent) - 10, 0)),
        (_("Revenue Growth -5%"), flt(revenue_growth_percent) - 5, expense_growth_percent, collection_rate_percent),
    ]
    for label, revenue_growth, expense_growth, collection_rate in sensitivity_tests:
        rows = build_projection_rows(revenue_growth, expense_growth, collection_rate, one_time_revenue, one_time_expense)
        test_profit = sum(row["revenue"] - row["expense"] for row in rows)
        sensitivity_rows.append([label, test_profit - base_profit, test_profit])

    return {
        "kpis": [
            _number_card(_("Projected FY Revenue"), projected_revenue, "Currency"),
            _number_card(_("Projected FY Expense"), projected_expense, "Currency"),
            _number_card(_("Projected FY Profit"), projected_profit, "Currency"),
            _number_card(_("Projected Net Margin"), projected_margin, "Percent"),
            _number_card(_("Estimated Collections"), estimated_collections, "Currency"),
            _number_card(_("Company Health Score"), health_score, "Int"),
            _number_card(_("Minimum Projected Cash"), minimum_projected_cash, "Currency"),
            _number_card(_("Break-Even Monthly Revenue"), break_even_revenue, "Currency"),
        ],
        "charts": [
            {
                "title": _("Projected P&L by Month"),
                "type": "bar",
                "fieldtype": "Currency",
                "points": [
                    {"label": row["month"], "value": row["net_profit"]}
                    for row in projected_rows
                ],
            },
            {
                "title": _("Projected Revenue by Month"),
                "type": "bar",
                "fieldtype": "Currency",
                "points": [
                    {"label": row["month"], "value": row["revenue"]}
                    for row in projected_rows
                ],
            },
            {
                "title": _("Projected Closing Cash by Month"),
                "type": "bar",
                "fieldtype": "Currency",
                "points": [
                    {"label": row["month"], "value": row["closing_cash"]}
                    for row in projected_rows
                ],
            },
        ],
        "tables": [
            {
                "title": _("Scenario Comparison"),
                "columns": [_("Scenario"), _("Revenue"), _("Expense"), _("Profit"), _("Margin"), _("Minimum Cash")],
                "rows": scenario_rows,
                "fieldtypes": ["Data", "Currency", "Currency", "Currency", "Percent", "Currency"],
            },
            {
                "title": _("Fiscal Year Projection"),
                "columns": [_("Month"), _("Revenue"), _("Expense"), _("P&L"), _("Type")],
                "rows": [
                    [row["month"], row["revenue"], row["expense"], row["net_profit"], row["type"]]
                    for row in projected_rows
                ],
                "fieldtypes": ["Data", "Currency", "Currency", "Currency", "Data"],
            },
            {
                "title": _("Cash Flow Projection"),
                "columns": [_("Month"), _("Collections"), _("Expenses"), _("Net Cash Flow"), _("Closing Cash"), _("Type")],
                "rows": [
                    [row["month"], row["collections"], row["expense"], row["net_cash_flow"], row["closing_cash"], row["type"]]
                    for row in projected_rows
                ],
                "fieldtypes": ["Data", "Currency", "Currency", "Currency", "Currency", "Data"],
            },
            {
                "title": _("Break-Even Analysis"),
                "columns": [_("Measure"), _("Value")],
                "rows": [
                    [_("Average Monthly Expense"), average_expense],
                    [_("Break-Even Monthly Revenue"), break_even_revenue],
                    [_("Required Daily Sales to Break Even"), required_daily_sales],
                    [_("Projected Remaining-Year Profit"), remaining_profit],
                ],
                "fieldtypes": ["Data", "Currency"],
            },
            {
                "title": _("Target Back-Solving"),
                "columns": [_("Target Question"), _("Answer")],
                "rows": [
                    [_("Profit Target"), flt(profit_target)],
                    [_("Projected Profit Gap"), required_profit_gap],
                    [_("Required Monthly Revenue Run Rate"), required_monthly_revenue],
                    [_("Monthly Expense Reduction Equivalent"), required_expense_reduction],
                ],
                "fieldtypes": ["Data", "Currency"],
            },
            {
                "title": _("Sensitivity Analysis"),
                "columns": [_("Change"), _("Profit Impact"), _("Projected Profit")],
                "rows": sensitivity_rows,
                "fieldtypes": ["Data", "Currency", "Currency"],
            },
            {
                "title": _("Simulation Assumptions"),
                "columns": [_("Assumption"), _("Value")],
                "rows": [
                    [_("Revenue Growth per Month"), f"{flt(revenue_growth_percent):,.2f}%"],
                    [_("Expense Growth per Month"), f"{flt(expense_growth_percent):,.2f}%"],
                    [_("Collection Rate"), f"{flt(collection_rate_percent):,.2f}%"],
                    [_("One-Time Revenue"), flt(one_time_revenue)],
                    [_("One-Time Expense"), flt(one_time_expense)],
                    [_("Profit Target"), flt(profit_target)],
                    [_("Minimum Cash Balance"), flt(minimum_cash_balance)],
                ],
                "fieldtypes": ["Data", "Data"],
            },
            {
                "title": _("Forecast Recommendations"),
                "columns": [_("Signal"), _("Recommendation")],
                "rows": recommendations,
                "fieldtypes": ["Data", "Data"],
            },
            {
                "title": _("Company Health Signals"),
                "columns": [_("Signal"), _("Value")],
                "rows": [
                    [_("Cash and Bank Balance"), cash_balance],
                    [_("Average Monthly Revenue"), average_revenue],
                    [_("Average Monthly Expense"), average_expense],
                    [_("Projected Expense Ratio"), f"{expense_ratio:,.2f}%"],
                    [_("Fiscal Year Ends"), fiscal_end],
                ],
                "fieldtypes": ["Data", "Data"],
            },
        ],
        "simulation": {
            "revenue_growth_percent": flt(revenue_growth_percent),
            "expense_growth_percent": flt(expense_growth_percent),
            "collection_rate_percent": flt(collection_rate_percent),
            "one_time_revenue": flt(one_time_revenue),
            "one_time_expense": flt(one_time_expense),
            "profit_target": flt(profit_target),
            "minimum_cash_balance": flt(minimum_cash_balance),
            "to_date": reference_date,
        },
        "notes": [
            _("Projection uses fiscal-year actual revenue and expenses from GL Entry, then forecasts remaining months from run-rate and assumptions."),
            _("Simulation figures are directional and should be reviewed against budgets, pipeline, and management commitments."),
        ],
    }


def _executive_overview(from_date: str, to_date: str) -> dict:
    notes = []
    values = {"from_date": from_date, "to_date": to_date}
    previous_from, previous_to = _previous_period(from_date, to_date)
    previous_values = {"from_date": previous_from, "to_date": previous_to}

    sales = 0
    previous_sales = 0
    invoices = 0
    outstanding = 0
    overdue_receivables = 0
    daily_sales = []
    receivable_risks = []
    sales_by_person = []
    outstanding_by_person = []
    if _doctype_exists("Sales Invoice"):
        sales = _sum(
            """
            select sum(base_net_total) as value
            from `tabSales Invoice`
            where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
            """,
            values,
        )
        previous_sales = _sum(
            """
            select sum(base_net_total) as value
            from `tabSales Invoice`
            where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
            """,
            previous_values,
        )
        invoices = _sum(
            """
            select count(*) as value
            from `tabSales Invoice`
            where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
            """,
            values,
        )
        outstanding = _sum(
            """
            select sum(outstanding_amount) as value
            from `tabSales Invoice`
            where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
            """,
            values,
        )
        overdue_receivables = _sum(
            """
            select sum(outstanding_amount) as value
            from `tabSales Invoice`
            where docstatus = 1
              and outstanding_amount > 0
              and due_date < %(to_date)s
            """,
            {"to_date": to_date},
        )
        daily_sales = _rows(
            """
            select posting_date as label, sum(base_net_total) as amount, count(*) as count
            from `tabSales Invoice`
            where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
            group by posting_date
            order by posting_date
            """,
            values,
        )
        receivable_risks = _rows(
            """
            select customer as label,
                   sum(outstanding_amount) as amount,
                   max(datediff(%(to_date)s, due_date)) as days
            from `tabSales Invoice`
            where docstatus = 1
              and outstanding_amount > 0
              and due_date < %(to_date)s
            group by customer
            order by amount desc
            limit 10
            """,
            {"to_date": to_date},
        )
    else:
        notes.append(_("Sales Invoice is not installed."))

    if _doctype_exists("Sales Invoice") and _doctype_exists("Sales Team"):
        sales_by_person = _rows(
            """
            select
                st.sales_person as label,
                sum(coalesce(st.allocated_amount, si.base_net_total * st.allocated_percentage / 100)) as amount,
                count(distinct si.name) as count
            from `tabSales Invoice` si
            inner join `tabSales Team` st
                on st.parent = si.name and st.parenttype = 'Sales Invoice'
            where si.docstatus = 1
              and si.posting_date between %(from_date)s and %(to_date)s
              and st.sales_person is not null
              and st.sales_person != ''
            group by st.sales_person
            order by amount desc
            limit 10
            """,
            values,
        )
        outstanding_by_person = _rows(
            """
            select
                st.sales_person as label,
                sum(si.outstanding_amount * coalesce(st.allocated_percentage, 100) / 100) as amount,
                count(distinct si.name) as count
            from `tabSales Invoice` si
            inner join `tabSales Team` st
                on st.parent = si.name and st.parenttype = 'Sales Invoice'
            where si.docstatus = 1
              and si.posting_date between %(from_date)s and %(to_date)s
              and si.outstanding_amount != 0
              and st.sales_person is not null
              and st.sales_person != ''
            group by st.sales_person
            having amount != 0
            order by amount desc
            limit 10
            """,
            values,
        )
    elif _doctype_exists("Sales Invoice"):
        notes.append(_("Sales Team is not available, so sales person performance is hidden."))

    income = 0
    expense = 0
    previous_income = 0
    previous_expense = 0
    if _doctype_exists("GL Entry") and _doctype_exists("Account"):
        income = _sum(
            """
            select sum(gle.credit - gle.debit) as value
            from `tabGL Entry` gle
            inner join `tabAccount` account on account.name = gle.account
            where gle.docstatus = 1
              and account.root_type = 'Income'
              and gle.posting_date between %(from_date)s and %(to_date)s
            """,
            values,
        )
        previous_income = _sum(
            """
            select sum(gle.credit - gle.debit) as value
            from `tabGL Entry` gle
            inner join `tabAccount` account on account.name = gle.account
            where gle.docstatus = 1
              and account.root_type = 'Income'
              and gle.posting_date between %(from_date)s and %(to_date)s
            """,
            previous_values,
        )
        expense = _sum(
            """
            select sum(gle.debit - gle.credit) as value
            from `tabGL Entry` gle
            inner join `tabAccount` account on account.name = gle.account
            where gle.docstatus = 1
              and account.root_type = 'Expense'
              and gle.posting_date between %(from_date)s and %(to_date)s
            """,
            values,
        )
        previous_expense = _sum(
            """
            select sum(gle.debit - gle.credit) as value
            from `tabGL Entry` gle
            inner join `tabAccount` account on account.name = gle.account
            where gle.docstatus = 1
              and account.root_type = 'Expense'
              and gle.posting_date between %(from_date)s and %(to_date)s
            """,
            previous_values,
        )
    else:
        notes.append(_("GL Entry or Account is not available."))

    net_profit = income - expense
    previous_profit = previous_income - previous_expense
    margin = (net_profit / income * 100) if income else 0
    cash_balance = _cash_balance(to_date)

    payable_due_soon = 0
    payable_overdue = 0
    payable_risks = []
    if _doctype_exists("Purchase Invoice"):
        payable_due_soon = _sum(
            """
            select sum(outstanding_amount) as value
            from `tabPurchase Invoice`
            where docstatus = 1
              and outstanding_amount > 0
              and due_date between %(to_date)s and %(due_to)s
            """,
            {"to_date": to_date, "due_to": str(add_days(getdate(to_date), 7))},
        )
        payable_overdue = _sum(
            """
            select sum(outstanding_amount) as value
            from `tabPurchase Invoice`
            where docstatus = 1
              and outstanding_amount > 0
              and due_date < %(to_date)s
            """,
            {"to_date": to_date},
        )
        payable_risks = _rows(
            """
            select supplier as label,
                   sum(outstanding_amount) as amount,
                   min(due_date) as due_date
            from `tabPurchase Invoice`
            where docstatus = 1
              and outstanding_amount > 0
              and due_date <= %(due_to)s
            group by supplier
            order by amount desc
            limit 10
            """,
            {"due_to": str(add_days(getdate(to_date), 7))},
        )

    risks = []
    if overdue_receivables:
        risks.append([_("Overdue Receivables"), overdue_receivables, _("Customer collections require attention.")])
    if payable_due_soon:
        risks.append([_("Payables Due in 7 Days"), payable_due_soon, _("Confirm cash coverage for upcoming supplier payments.")])
    if payable_overdue:
        risks.append([_("Overdue Payables"), payable_overdue, _("Supplier obligations are already overdue.")])
    if expense > sales and sales:
        risks.append([_("Expense Above Sales"), expense - sales, _("Expenses exceeded sales in the selected period.")])

    opportunities = [
        [row.label, row.amount, _("High-performing salesperson; review pipeline and repeatable actions.")]
        for row in sales_by_person[:5]
    ]

    return {
        "kpis": [
            _number_card(_("Net Sales"), sales, "Currency", _list_route("Sales Invoice", {"docstatus": 1, **_period_filter("posting_date", from_date, to_date)})),
            _number_card(_("Sales Change"), _change_percent(sales, previous_sales), "Percent"),
            _number_card(_("Sales Invoices"), invoices, "Int", _list_route("Sales Invoice", {"docstatus": 1, **_period_filter("posting_date", from_date, to_date)})),
            _number_card(_("Expense"), expense, "Currency", _report_route("General Ledger", {"from_date": from_date, "to_date": to_date})),
            _number_card(_("Outstanding Sales"), outstanding, "Currency", _report_route("Accounts Receivable", {"report_date": to_date})),
            _number_card(_("Overdue Receivables"), overdue_receivables, "Currency", _report_route("Accounts Receivable", {"report_date": to_date, "range3": 90})),
            _number_card(_("Cash and Bank Balance"), cash_balance, "Currency", _report_route("General Ledger", {"to_date": to_date})),
            _number_card(_("Payables Due Soon"), payable_due_soon, "Currency", _report_route("Accounts Payable", {"report_date": to_date})),
            _number_card(_("Net Profit"), net_profit, "Currency", _report_route("Profit and Loss Statement", {"from_date": from_date, "to_date": to_date})),
            _number_card(_("Profit Change"), _change_percent(net_profit, previous_profit), "Percent"),
            _number_card(_("Net Margin"), margin, "Percent", _report_route("Profit and Loss Statement", {"from_date": from_date, "to_date": to_date})),
        ],
        "charts": [
            {
                "title": _("Daily Sales Performance"),
                "type": "bar",
                "fieldtype": "Currency",
                "points": [
                    {
                        "label": str(row.label),
                        "value": row.amount,
                        "route": _list_route("Sales Invoice", {"docstatus": 1, "posting_date": str(row.label)}),
                    }
                    for row in daily_sales
                ],
            },
            {
                "title": _("Sales Person Performance"),
                "type": "bar",
                "fieldtype": "Currency",
                "points": [
                    {"label": row.label, "value": row.amount}
                    for row in sales_by_person[:8]
                ],
            },
        ],
        "tables": [
            {
                "title": _("Daily Sales Performance"),
                "columns": [_("Date"), _("Sales"), _("Invoices")],
                "rows": [[row.label, row.amount, row.count] for row in daily_sales],
                "fieldtypes": ["Date", "Currency", "Int"],
                "row_routes": [
                    _list_route("Sales Invoice", {"docstatus": 1, "posting_date": str(row.label)})
                    for row in daily_sales
                ],
            },
            {
                "title": _("Sales Person Performance"),
                "columns": [_("Sales Person"), _("Allocated Sales"), _("Invoices")],
                "rows": [[row.label, row.amount, row.count] for row in sales_by_person],
                "fieldtypes": ["Data", "Currency", "Int"],
            },
            {
                "title": _("Outstanding by Sales Person"),
                "columns": [_("Sales Person"), _("Allocated Outstanding"), _("Invoices")],
                "rows": [[row.label, row.amount, row.count] for row in outstanding_by_person],
                "fieldtypes": ["Data", "Currency", "Int"],
            },
            {
                "title": _("Top Receivables Risks"),
                "columns": [_("Customer"), _("Overdue Amount"), _("Max Days Overdue")],
                "rows": [[row.label, row.amount, row.days] for row in receivable_risks],
                "fieldtypes": ["Data", "Currency", "Int"],
                "row_routes": [
                    _report_route("Accounts Receivable", {"report_date": to_date, "customer": row.label})
                    for row in receivable_risks
                ],
            },
            {
                "title": _("Upcoming Payables Pressure"),
                "columns": [_("Supplier"), _("Amount"), _("Earliest Due Date")],
                "rows": [[row.label, row.amount, row.due_date] for row in payable_risks],
                "fieldtypes": ["Data", "Currency", "Date"],
                "row_routes": [
                    _report_route("Accounts Payable", {"report_date": to_date, "supplier": row.label})
                    for row in payable_risks
                ],
            },
            {
                "title": _("Executive Risks"),
                "columns": [_("Signal"), _("Value"), _("Action")],
                "rows": risks,
                "fieldtypes": ["Data", "Currency", "Data"],
            },
            {
                "title": _("Sales Opportunities"),
                "columns": [_("Sales Person"), _("Allocated Sales"), _("Action")],
                "rows": opportunities,
                "fieldtypes": ["Data", "Currency", "Data"],
            },
        ],
        "notes": notes,
    }


def _expense(from_date: str, to_date: str) -> dict:
    values = {"from_date": from_date, "to_date": to_date}
    notes = []

    expense_from_gl = 0
    top_accounts = []
    if _doctype_exists("GL Entry") and _doctype_exists("Account"):
        expense_from_gl = _sum(
            """
            select sum(gle.debit - gle.credit) as value
            from `tabGL Entry` gle
            inner join `tabAccount` account on account.name = gle.account
            where gle.docstatus = 1
              and account.root_type = 'Expense'
              and gle.posting_date between %(from_date)s and %(to_date)s
            """,
            values,
        )
        top_accounts = _rows(
            """
            select gle.account as label, sum(gle.debit - gle.credit) as amount
            from `tabGL Entry` gle
            inner join `tabAccount` account on account.name = gle.account
            where gle.docstatus = 1
              and account.root_type = 'Expense'
              and gle.posting_date between %(from_date)s and %(to_date)s
            group by gle.account
            having amount != 0
            order by amount desc
            limit 10
            """,
            values,
        )
    else:
        notes.append(_("GL Entry or Account is not available."))

    purchase_invoice_expense = 0
    if _doctype_exists("Purchase Invoice"):
        purchase_invoice_expense = _sum(
            """
            select sum(base_net_total) as value
            from `tabPurchase Invoice`
            where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
            """,
            values,
        )

    expense_claims = 0
    if _doctype_exists("Expense Claim"):
        expense_claims = _sum(
            """
            select sum(total_claimed_amount) as value
            from `tabExpense Claim`
            where docstatus = 1 and posting_date between %(from_date)s and %(to_date)s
            """,
            values,
        )

    return {
        "kpis": [
            _number_card(_("Total Expense"), expense_from_gl, "Currency", _report_route("General Ledger", {"from_date": from_date, "to_date": to_date})),
            _number_card(_("Purchase Invoice Expense"), purchase_invoice_expense, "Currency", _list_route("Purchase Invoice", {"docstatus": 1, **_period_filter("posting_date", from_date, to_date)})),
            _number_card(_("Expense Claims"), expense_claims, "Currency", _list_route("Expense Claim", {"docstatus": 1, **_period_filter("posting_date", from_date, to_date)})),
            _number_card(_("Top Expense Accounts"), len(top_accounts), "Int"),
        ],
        "tables": [
            {
                "title": _("Top Expense Accounts"),
                "columns": [_("Account"), _("Amount")],
                "rows": [[row.label, row.amount] for row in top_accounts],
                "fieldtypes": ["Data", "Currency"],
                "row_routes": [
                    _report_route("General Ledger", {"account": row.label, "from_date": from_date, "to_date": to_date})
                    for row in top_accounts
                ],
            }
        ],
        "notes": notes,
    }


def _profit_and_loss(from_date: str, to_date: str) -> dict:
    if not (_doctype_exists("GL Entry") and _doctype_exists("Account")):
        return {"kpis": [], "tables": [], "notes": [_("GL Entry or Account is not available.")]}

    values = {"from_date": from_date, "to_date": to_date}
    income = _sum(
        """
        select sum(gle.credit - gle.debit) as value
        from `tabGL Entry` gle
        inner join `tabAccount` account on account.name = gle.account
        where gle.docstatus = 1
          and account.root_type = 'Income'
          and gle.posting_date between %(from_date)s and %(to_date)s
        """,
        values,
    )
    expense = _sum(
        """
        select sum(gle.debit - gle.credit) as value
        from `tabGL Entry` gle
        inner join `tabAccount` account on account.name = gle.account
        where gle.docstatus = 1
          and account.root_type = 'Expense'
          and gle.posting_date between %(from_date)s and %(to_date)s
        """,
        values,
    )
    net_profit = income - expense
    margin = (net_profit / income * 100) if income else 0

    account_summary = _rows(
        """
        select account.root_type, gle.account as label,
               sum(case
                   when account.root_type = 'Income' then gle.credit - gle.debit
                   when account.root_type = 'Expense' then gle.debit - gle.credit
                   else 0
               end) as amount
        from `tabGL Entry` gle
        inner join `tabAccount` account on account.name = gle.account
        where gle.docstatus = 1
          and account.root_type in ('Income', 'Expense')
          and gle.posting_date between %(from_date)s and %(to_date)s
        group by account.root_type, gle.account
        having amount != 0
        order by account.root_type, amount desc
        limit 20
        """,
        values,
    )

    return {
        "kpis": [
            _number_card(_("Income"), income, "Currency", _report_route("Profit and Loss Statement", {"from_date": from_date, "to_date": to_date})),
            _number_card(_("Expense"), expense, "Currency", _report_route("Profit and Loss Statement", {"from_date": from_date, "to_date": to_date})),
            _number_card(_("Net Profit"), net_profit, "Currency", _report_route("Profit and Loss Statement", {"from_date": from_date, "to_date": to_date})),
            _number_card(_("Net Margin"), margin, "Percent", _report_route("Profit and Loss Statement", {"from_date": from_date, "to_date": to_date})),
        ],
        "tables": [
            {
                "title": _("Income and Expense Accounts"),
                "columns": [_("Type"), _("Account"), _("Amount")],
                "rows": [[row.root_type, row.label, row.amount] for row in account_summary],
                "fieldtypes": ["Data", "Data", "Currency"],
                "row_routes": [
                    _report_route("General Ledger", {"account": row.label, "from_date": from_date, "to_date": to_date})
                    for row in account_summary
                ],
            }
        ],
    }


def _system_usage(from_date: str, to_date: str) -> dict:
    values = {"from_date": from_date, "to_date": to_date}
    notes = []

    active_users = _sum(
        """
        select count(*) as value
        from `tabUser`
        where enabled = 1 and user_type = 'System User'
        """,
        values,
    )
    new_records = 0
    modified_records = 0
    activity_by_user = []

    if _doctype_exists("Activity Log"):
        new_records = _sum(
            """
            select count(*) as value
            from `tabActivity Log`
            where date(creation) between %(from_date)s and %(to_date)s
            """,
            values,
        )
        activity_by_user = _rows(
            """
            select user as label, count(*) as count
            from `tabActivity Log`
            where date(creation) between %(from_date)s and %(to_date)s
              and user not in ('Administrator', 'Guest')
            group by user
            order by count desc
            limit 10
            """,
            values,
        )

    if _doctype_exists("Version"):
        modified_records = _sum(
            """
            select count(*) as value
            from `tabVersion`
            where date(creation) between %(from_date)s and %(to_date)s
            """,
            values,
        )

    sales_person_heatmap, sales_person_interactions, usage_notes = _sales_person_usage(from_date, to_date)
    notes.extend(usage_notes)

    return {
        "kpis": [
            _number_card(_("Active System Users"), active_users, "Int", _list_route("User", {"enabled": 1, "user_type": "System User"})),
            _number_card(_("Activity Events"), new_records, "Int", _list_route("Activity Log", _period_filter("creation", from_date, to_date))),
            _number_card(_("Document Changes"), modified_records, "Int", _list_route("Version", _period_filter("creation", from_date, to_date))),
            _number_card(_("Active Users in Period"), len(activity_by_user), "Int"),
        ],
        "tables": [
            {
                "title": _("Most Active Users"),
                "columns": [_("User"), _("Events")],
                "rows": [[row.label, row.count] for row in activity_by_user],
                "fieldtypes": ["Data", "Int"],
            },
            {
                "title": _("Sales Person System Areas"),
                "columns": [_("Sales Person"), _("System Area"), _("Interactions")],
                "rows": [
                    [row["sales_person"], row["system_area"], row["count"]]
                    for row in sales_person_interactions
                ],
                "fieldtypes": ["Data", "Data", "Int"],
            }
        ],
        "heatmaps": [
            {
                "title": _("Sales Person Usage Heatmap"),
                "columns": _date_columns(from_date, to_date),
                "rows": sales_person_heatmap,
                "fieldtype": "Int",
            }
        ],
        "notes": notes,
    }


def _with_empty_defaults(section: dict) -> dict:
    section.setdefault("kpis", [])
    section.setdefault("charts", [])
    section.setdefault("tables", [])
    section.setdefault("heatmaps", [])
    section.setdefault("notes", [])
    return section


@frappe.whitelist()
def get_dashboard(from_date: str | None = None, to_date: str | None = None) -> dict:
    require_executive_report_access()
    return get_dashboard_for_email(from_date=from_date, to_date=to_date)


def get_dashboard_for_email(from_date: str | None = None, to_date: str | None = None) -> dict:
    from_date, to_date = _default_dates(from_date, to_date)
    return {
        "from_date": from_date,
        "to_date": to_date,
        "currency": _get_company_currency(),
        "tabs": {
            "overview": _with_empty_defaults(_executive_overview(from_date, to_date)),
            "sales": _with_empty_defaults(_sales(from_date, to_date)),
            "expense": _with_empty_defaults(_expense(from_date, to_date)),
            "profit_loss": _with_empty_defaults(_profit_and_loss(from_date, to_date)),
            "system_usage": _with_empty_defaults(_system_usage(from_date, to_date)),
            "projection": _with_empty_defaults(_projection_and_simulation(to_date=to_date)),
        },
    }


@frappe.whitelist()
def run_projection_simulation(
    to_date: str | None = None,
    revenue_growth_percent: float = 0,
    expense_growth_percent: float = 0,
    collection_rate_percent: float = 75,
    one_time_revenue: float = 0,
    one_time_expense: float = 0,
    profit_target: float = 0,
    minimum_cash_balance: float = 0,
) -> dict:
    require_executive_report_access()
    return _with_empty_defaults(
        _projection_and_simulation(
            to_date=to_date,
            revenue_growth_percent=flt(revenue_growth_percent),
            expense_growth_percent=flt(expense_growth_percent),
            collection_rate_percent=flt(collection_rate_percent),
            one_time_revenue=flt(one_time_revenue),
            one_time_expense=flt(one_time_expense),
            profit_target=flt(profit_target),
            minimum_cash_balance=flt(minimum_cash_balance),
        )
    )


def get_enabled_recipients() -> list[str]:
    settings = frappe.get_single("Executive Report Settings")
    return [
        row.email.strip().lower()
        for row in settings.recipients
        if row.enabled and row.email and row.email.strip()
    ]


def format_value(value, fieldtype: str, currency: str | None = None) -> str:
    if fieldtype == "Currency":
        return frappe.format_value(value, {"fieldtype": "Currency", "options": currency})
    if fieldtype == "Percent":
        return f"{flt(value):,.2f}%"
    if fieldtype == "Int":
        return f"{int(flt(value)):,}"
    return frappe.format_value(value, {"fieldtype": fieldtype})


def iter_kpis(dashboard: dict) -> Iterable[tuple[str, dict]]:
    labels = {
        "overview": _("Executive Overview"),
        "sales": _("Sales"),
        "expense": _("Expense"),
        "profit_loss": _("Profit and Loss"),
        "system_usage": _("System Usage"),
        "projection": _("Projection and Simulation"),
    }
    for key, tab in dashboard["tabs"].items():
        for kpi in tab.get("kpis", []):
            yield labels.get(key, key), kpi
