srv_erp.package_barcode.install_item_link_formatter = function () {
	if (srv_erp.package_barcode.item_link_formatter_installed) {
		return;
	}

	const existing_formatter = frappe.form.link_formatters.Item;
	frappe.form.link_formatters.Item = function (value, doc, docfield) {
		const settings = srv_erp.package_barcode.stock_table_display;
		const should_format =
			settings.show_item_name_before_item_code &&
			doc &&
			srv_erp.package_barcode.stock_child_doctypes.has(doc.doctype) &&
			docfield?.fieldname === "item_code" &&
			doc.item_name &&
			value;

		if (should_format) {
			return `${doc.item_name}: ${value}`;
		}

		if (existing_formatter) {
			return existing_formatter(value, doc, docfield);
		}

		return value;
	};

	srv_erp.package_barcode.item_link_formatter_installed = true;
};

srv_erp.package_barcode.load_stock_table_display_settings = function (frm) {
	if (srv_erp.package_barcode.stock_table_display.loaded) {
		srv_erp.package_barcode.refresh_item_grids(frm);
		return;
	}
	if (srv_erp.package_barcode.stock_table_display.loading) {
		return;
	}

	srv_erp.package_barcode.stock_table_display.loading = true;
	frappe.call({
		method: "srv_erp.package_barcode.api.get_stock_table_display_settings",
		callback(r) {
			srv_erp.package_barcode.stock_table_display = {
				loaded: true,
				loading: false,
				show_item_name_before_item_code: Boolean(r.message?.show_item_name_before_item_code),
			};

			srv_erp.package_barcode.refresh_item_grids(frm);
		},
		error() {
			srv_erp.package_barcode.stock_table_display.loading = false;
		},
	});
};

srv_erp.package_barcode.refresh_item_grids = function (frm) {
	["items"].forEach((fieldname) => {
		const grid = frm.fields_dict[fieldname]?.grid;
		grid?.refresh();
	});
};
