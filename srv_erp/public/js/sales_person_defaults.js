frappe.provide("srv_erp.sales_person_defaults");

srv_erp.sales_person_defaults.get_mapped_sales_person = async function () {
	if (srv_erp.sales_person_defaults.sales_person !== undefined) {
		return srv_erp.sales_person_defaults.sales_person;
	}

	const response = await frappe.call({
		method: "srv_erp.sales_person_user_mapping.get_mapped_sales_person",
	});
	srv_erp.sales_person_defaults.sales_person = response.message || null;
	return srv_erp.sales_person_defaults.sales_person;
};

srv_erp.sales_person_defaults.set_sales_person = async function (frm) {
	if (!frm || frm.doc.docstatus) {
		return;
	}
	if (!frm.fields_dict.sales_person || frm.doc.sales_person) {
		return;
	}

	const sales_person = await srv_erp.sales_person_defaults.get_mapped_sales_person();
	if (sales_person && !frm.doc.sales_person) {
		frm.set_value("sales_person", sales_person);
	}
};

$(document).on("form-refresh", function (event, frm) {
	srv_erp.sales_person_defaults.set_sales_person(frm);
});
