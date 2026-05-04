# Executive Report

Executive Report is a Frappe/ERPNext v16 app that adds an executive dashboard for:

- Sales performance
- Expense performance
- Profit and loss performance
- ERPNext system usage performance

It also includes settings for choosing email recipients who should receive a daily performance summary.

## Install

From your bench folder:

```bash
bench get-app /path/to/executive_report
bench --site your-site.local install-app executive_report
bench --site your-site.local migrate
bench restart
```

Open **Executive Dashboard** from Desk, and configure recipients in **Executive Report Settings**.

