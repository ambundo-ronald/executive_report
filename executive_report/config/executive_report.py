from frappe import _


def get_data():
    return [
        {
            "label": _("Executive Report"),
            "items": [
                {
                    "type": "page",
                    "name": "executive-dashboard",
                    "label": _("Executive Dashboard"),
                    "description": _("View sales, expense, profit and loss, and system usage performance."),
                },
                {
                    "type": "doctype",
                    "name": "Executive Report Settings",
                    "label": _("Executive Report Settings"),
                    "description": _("Configure daily executive performance email recipients."),
                },
            ],
        }
    ]

