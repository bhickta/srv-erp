frappe.ui.form.on("Masters Settings", {
	refresh(frm) {
		if (!frm.is_new() && frm.perm[0]?.write) {
			frm.add_custom_button(__("Refresh Profiles and Item Grids"), () => {
				frappe.call({
					method: "srv_erp.masters.dynamic_item.api.refresh_masters_configuration",
					freeze: true,
					callback(response) {
						const result = response.message || {};
						frappe.msgprint(
							__("Created {0} profiles and added {1} Item grids.", [
								result.profiles_created || 0,
								result.grids_added || 0,
							])
						);
						frm.reload_doc();
					},
				});
			});
		}
	},
});
