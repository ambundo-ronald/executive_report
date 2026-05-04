frappe.ui.form.on("Executive Report Settings", {
    refresh(frm) {
        if (!frappe.user.has_role("Executive Report Manager")) {
            return;
        }

        frm.add_custom_button(__("Send Summary Now"), () => {
            frappe.call({
                method: "executive_report.executive_report.email.send_summary_now",
                freeze: true,
                freeze_message: __("Sending summary email..."),
                callback() {
                    frappe.show_alert({
                        message: __("Executive summary email queued."),
                        indicator: "green",
                    });
                },
            });
        });
    },
});
