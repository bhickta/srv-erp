frappe.ui.form.on("Dynamic Item Request", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call({
			method: "srv_erp.masters.dynamic_item.api.get_dynamic_item_request_status",
			args: { request: frm.doc.name },
			callback(response) {
				const status = response.message || {};
				if (status.can_approve) {
					frm.add_custom_button(__("Approve"), () => approve_request(frm), __("Actions"));
				}
				if (status.can_reject) {
					frm.add_custom_button(__("Reject"), () => reject_request(frm), __("Actions"));
				}
				if (status.can_cancel) {
					frm.add_custom_button(__("Cancel Request"), () => cancel_request(frm), __("Actions"));
				}
			},
		});
	},
});

function approve_request(frm) {
	frappe.confirm(__("Approve this request and make its Item configuration available?"), () => {
		frappe.call({
			method: "srv_erp.masters.dynamic_item.api.approve_dynamic_item_request",
			args: { request: frm.doc.name },
			freeze: true,
			freeze_message: __("Approving Item..."),
			callback: () => frm.reload_doc(),
		});
	});
}

function reject_request(frm) {
	frappe.prompt(
		[
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Rejection Reason"),
				reqd: 1,
			},
		],
		(values) => {
			frappe.call({
				method: "srv_erp.masters.dynamic_item.api.reject_dynamic_item_request",
				args: { request: frm.doc.name, reason: values.reason },
				freeze: true,
				freeze_message: __("Rejecting request..."),
				callback: () => frm.reload_doc(),
			});
		},
		__("Reject Dynamic Item Request"),
		__("Reject")
	);
}

function cancel_request(frm) {
	frappe.confirm(__("Cancel this request and delete its unreferenced staged Item?"), () => {
		frappe.call({
			method: "srv_erp.masters.dynamic_item.api.cancel_dynamic_item_request",
			args: { request: frm.doc.name },
			freeze: true,
			callback: () => frm.reload_doc(),
		});
	});
}
