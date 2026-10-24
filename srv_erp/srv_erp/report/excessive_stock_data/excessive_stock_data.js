frappe.query_reports["Excessive Stock Data"] = {
    filters: [
        {
            fieldname: "item_code",
            label: __("Item"),
            fieldtype: "Link",
            options: "Item",
        },
        {
            fieldname: "item_group",
            label: __("Item Group"),
            fieldtype: "Link",
            options: "Item Group",
        },
        {
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse",
            default: "Finished Goods - SE",
            reqd: 1,
        },
        {
            fieldname: "uom",
            label: __("UOM"),
            fieldtype: "Link",
            options: "UOM",
        },
        {
            fieldname: "brand",
            label: __("Brand"),
            fieldtype: "Link",
            options: "Brand",
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer",
        },
    ],
};
