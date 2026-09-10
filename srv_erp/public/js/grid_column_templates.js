/* global srv_erp */

frappe.provide("srv_erp.grid_columns");

srv_erp.grid_columns.get_boot_config = function () {
	return frappe.boot.srv_erp_grid_columns || { can_publish: false, templates: {} };
};

srv_erp.grid_columns.get_template = function (parent_doctype, child_doctype) {
	const templates = srv_erp.grid_columns.get_boot_config().templates || {};
	return templates[parent_doctype]?.[child_doctype] || null;
};

const standard_setup_user_defined_columns =
	frappe.ui.form.Grid.prototype.setup_user_defined_columns;

frappe.ui.form.Grid.prototype.setup_user_defined_columns = function () {
	if (this.frm) {
		const template = srv_erp.grid_columns.get_template(this.frm.doctype, this.doctype);
		if (template?.length) {
			const settings = (frappe.model.user_settings[this.frm.doctype] ||= {});
			const grid_settings = (settings.GridView ||= {});
			grid_settings[this.doctype] = template;
		}
	}

	return standard_setup_user_defined_columns.apply(this, arguments);
};

const standard_configure_columns =
	frappe.ui.form.GridRow.prototype.configure_dialog_for_columns_selector;

frappe.ui.form.GridRow.prototype.configure_dialog_for_columns_selector = function () {
	standard_configure_columns.apply(this, arguments);

	if (!this.frm || !srv_erp.grid_columns.get_boot_config().can_publish) {
		return;
	}

	this.grid_settings_dialog.add_custom_action(__("Publish to All Users"), () => {
		this.validate_columns_width();
		if (!this.selected_columns_for_grid?.length) {
			frappe.throw(__("Select at least one grid column."));
		}

		frappe.confirm(
			__("Use these {0} columns for every user?", [__(this.grid.doctype)]),
			() => {
				frappe.call({
					method: "srv_erp.grid_column_templates.publish_grid_columns",
					args: {
						parent_doctype: this.frm.doctype,
						child_doctype: this.grid.doctype,
						columns: this.selected_columns_for_grid,
					},
					freeze: true,
					freeze_message: __("Publishing grid columns..."),
					callback: (response) => {
						const published = response.message;
						const config = srv_erp.grid_columns.get_boot_config();
						config.templates[published.parent_doctype] ||= {};
						config.templates[published.parent_doctype][published.child_doctype] =
							published.columns;
						this.grid.visible_columns = [];
						this.grid.reset_grid();
						this.grid_settings_dialog.hide();
						frappe.show_alert({
							message: __("Grid columns published to all users."),
							indicator: "green",
						});
					},
				});
			}
		);
	});
};
