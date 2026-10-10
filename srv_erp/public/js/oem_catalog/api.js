frappe.provide('srv_erp.oem');
srv_erp.oem.call = async function (method, args = {}) {
    const response = await frappe.call({method: `srv_erp.oem_catalog.api.${method}`, args});
    return response.message;
};
srv_erp.oem.uuid = () => crypto.randomUUID();
srv_erp.oem.escape = (value) => frappe.utils.escape_html(String(value ?? ''));
