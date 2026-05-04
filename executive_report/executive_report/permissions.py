import frappe
from frappe import _


EXECUTIVE_REPORT_USER_ROLES = {"Executive Report User", "Executive Report Manager"}
EXECUTIVE_REPORT_MANAGER_ROLES = {"Executive Report Manager"}


def require_executive_report_access() -> None:
    if frappe.session.user == "Administrator":
        return

    if not EXECUTIVE_REPORT_USER_ROLES.intersection(frappe.get_roles()):
        frappe.throw(
            _("You need the Executive Report User role to access this dashboard."),
            frappe.PermissionError,
        )


def require_executive_report_manager() -> None:
    if frappe.session.user == "Administrator":
        return

    if not EXECUTIVE_REPORT_MANAGER_ROLES.intersection(frappe.get_roles()):
        frappe.throw(
            _("You need the Executive Report Manager role to manage executive reports."),
            frappe.PermissionError,
        )

