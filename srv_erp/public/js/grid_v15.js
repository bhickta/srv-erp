frappe.provide('srv_erp.grid_v15');
srv_erp.grid_v15.installers = [];
// v15 exports Grid/GridRow as ES modules; obtain their real prototypes from
// table instances instead of relying on nonexistent global constructors.
frappe.require('controls.bundle.js', () => {
    const standard_refresh = frappe.ui.form.ControlTable.prototype.refresh_input;
    frappe.ui.form.ControlTable.prototype.refresh_input = function () {
        const result = standard_refresh.apply(this, arguments);
        srv_erp.grid_v15.installers.forEach(install => install(this.grid));
        return result;
    };
});
