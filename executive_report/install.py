import frappe


EXECUTIVE_REPORT_ROLES = (
    "Executive Report User",
    "Executive Report Manager",
)


def before_install():
    for role_name in EXECUTIVE_REPORT_ROLES:
        if frappe.db.exists("Role", role_name):
            continue

        role = frappe.new_doc("Role")
        role.role_name = role_name
        role.desk_access = 1
        role.is_custom = 1
        role.insert(ignore_permissions=True)

