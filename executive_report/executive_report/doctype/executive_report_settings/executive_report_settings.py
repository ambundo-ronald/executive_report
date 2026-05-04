import frappe
from frappe.model.document import Document
from frappe.utils import validate_email_address


class ExecutiveReportSettings(Document):
    def validate(self):
        if not self.send_time:
            frappe.throw("Send Time is required.")

        seen = set()
        for row in self.recipients:
            if not row.email:
                continue

            row.email = row.email.strip().lower()
            validate_email_address(row.email, throw=True)

            if row.email in seen:
                frappe.throw(f"Duplicate recipient email: {row.email}")

            seen.add(row.email)
