app_name = "executive_report"
app_title = "Executive Report"
app_publisher = "Executive Report App"
app_description = "Executive dashboard and daily performance summaries for ERPNext."
app_email = "admin@example.com"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

app_include_css = "/assets/executive_report/css/executive_report.css"

before_install = "executive_report.install.before_install"

fixtures = [
    {
        "dt": "Role",
        "filters": [
            ["role_name", "in", ["Executive Report User", "Executive Report Manager"]],
        ],
    },
]

scheduler_events = {
    "all": [
        "executive_report.executive_report.email.send_daily_summary",
    ],
}
