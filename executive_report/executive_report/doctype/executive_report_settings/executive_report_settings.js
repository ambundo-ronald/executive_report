frappe.ui.form.on("Executive Report Settings", {
    refresh(frm) {
        if (!frappe.user.has_role("Executive Report Manager")) {
            return;
        }

        frm.add_custom_button(__("Send Summary Now"), () => {
            const today = frappe.datetime.get_today();
            const dialog = new frappe.ui.Dialog({
                title: __("Send Executive Summary"),
                fields: [
                    {
                        fieldname: "from_date",
                        label: __("From Date"),
                        fieldtype: "Date",
                        default: today,
                        reqd: 1,
                    },
                    {
                        fieldname: "to_date",
                        label: __("To Date"),
                        fieldtype: "Date",
                        default: today,
                        reqd: 1,
                    },
                ],
                primary_action_label: __("Send Now"),
                primary_action(values) {
                    if (values.from_date > values.to_date) {
                        frappe.msgprint(__("From Date cannot be after To Date."));
                        return;
                    }

                    dialog.hide();
                    frappe.call({
                        method: "executive_report.executive_report.email.send_summary_now",
                        args: {
                            from_date: values.from_date,
                            to_date: values.to_date,
                        },
                        freeze: true,
                        freeze_message: __("Sending summary email..."),
                        callback() {
                            frappe.show_alert({
                                message: __("Executive summary email queued."),
                                indicator: "green",
                            });
                        },
                    });
                },
            });
            dialog.show();
        });
    },
});
