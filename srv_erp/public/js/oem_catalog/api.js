frappe.provide('srv_erp.oem');
srv_erp.oem.call = async function (method, args = {}) {
    const response = await frappe.call({method: `srv_erp.oem_catalog.api.${method}`, args});
    return response.message;
};
srv_erp.oem.uuid = () => crypto.randomUUID();
srv_erp.oem.escape = (value) => frappe.utils.escape_html(String(value ?? ''));
srv_erp.oem._ui_settings = null;
srv_erp.oem.get_ui_settings = async function () {
    if (!srv_erp.oem._ui_settings) srv_erp.oem._ui_settings = await srv_erp.oem.call('get_ui_settings');
    return srv_erp.oem._ui_settings;
};
// Returns null when the Brand picker must NOT be scoped (no customer, or
// governance off); otherwise the customer's authorized brands [{value,label,default}].
// Mirrors the server rule in permissions.authorize_context so the picker can never
// offer a brand the command would later reject.
srv_erp.oem.customer_brands = async function (customer, company) {
    if (!customer) return null;
    try {
        const settings = await srv_erp.oem.get_ui_settings();
        if (!settings.require_customer_brand) return null;
        const source_context = company ? {customer, company} : {customer};
        const result = await srv_erp.oem.call('get_context', {source_context});
        return result.brands || [];
    } catch (error) {
        return null;
    }
};
srv_erp.oem.brand_query = function (brands) {
    if (brands === null) return {};
    const names = brands.map(brand => brand.value);
    return {filters: {name: names.length ? ['in', names] : ['=', '__no_authorized_brand__']}};
};
