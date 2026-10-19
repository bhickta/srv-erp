frappe.query_reports["Stock Inward Register"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_end(),
            reqd: 1,
        },
        {
            fieldname: "voucher_type",
            label: __("Voucher Type"),
            fieldtype: "Select",
            options: "\nPurchase Receipt\nStock Entry",
        },
        {
            fieldname: "voucher_no",
            label: __("Voucher"),
            fieldtype: "Dynamic Link",
            options: "voucher_type",
        },
        {
            fieldname: "stock_entry_type",
            label: __("Stock Entry Type"),
            fieldtype: "Link",
            options: "Stock Entry Type",
        },
        {
            fieldname: "supplier",
            label: __("Supplier"),
            fieldtype: "Link",
            options: "Supplier",
        },
        {
            fieldname: "supplier_group",
            label: __("Supplier Group"),
            fieldtype: "Link",
            options: "Supplier Group",
        },
        {
            fieldname: "supplier_delivery_note",
            label: __("Supplier Delivery Note"),
            fieldtype: "Data",
        },
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
            fieldname: "brand",
            label: __("Brand"),
            fieldtype: "Link",
            options: "Brand",
        },
        {
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse",
        },
        {
            fieldname: "source_warehouse",
            label: __("Source Warehouse"),
            fieldtype: "Link",
            options: "Warehouse",
        },
        {
            fieldname: "purchase_order",
            label: __("Purchase Order"),
            fieldtype: "Link",
            options: "Purchase Order",
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "Link",
            options: "Project",
        },
        {
            fieldname: "batch_no",
            label: __("Batch No"),
            fieldtype: "Link",
            options: "Batch",
        },
        {
            fieldname: "price_list",
            label: __("Price List"),
            fieldtype: "Link",
            options: "Price List",
        },
        {
            fieldname: "group_by",
            label: __("Group By"),
            fieldtype: "Select",
            options: [
                "",
                "Voucher",
                "Voucher Type",
                "Supplier",
                "Supplier Group",
                "Item",
                "Item Group",
                "Warehouse",
                "Posting Date",
                "Stock Entry Type",
            ].join("\n"),
            default: "Item",
        },
        {
            fieldname: "sort_by",
            label: __("Sort By"),
            fieldtype: "Select",
            options: [
                "Posting Date",
                "Voucher",
                "Supplier",
                "Item",
                "Item Group",
                "Warehouse",
                "Quantity",
                "Stock Value",
            ].join("\n"),
            default: "Posting Date",
        },
        {
            fieldname: "sort_order",
            label: __("Sort Order"),
            fieldtype: "Select",
            options: "Descending\nAscending",
            default: "Descending",
        },
    ],

    formatter: function (
        value,
        row,
        column,
        data,
        default_formatter
    ) {
        value = default_formatter(
            value,
            row,
            column,
            data
        );

        if (
            column.fieldname === "voucher" &&
            data &&
            data.vouchers
        ) {
            const label =
                Number(data.voucher_count) === 1
                    ? "1 Voucher"
                    : `${data.voucher_count} Vouchers`;

            value = `
                <a
                    href="javascript:void(0)"
                    class="stock-inward-voucher-link"
                    data-vouchers="${encodeURIComponent(data.vouchers)}"
                >
                    ${label}
                </a>
            `;
        }

        return value;
    },

    onload: function (report) {
        $(report.page.wrapper).on(
            "click.stock_inward_register",
            ".stock-inward-voucher-link",
            function (e) {
                e.preventDefault();
                e.stopPropagation();

                const voucher_string = decodeURIComponent(
                    $(this).attr("data-vouchers")
                );

                show_voucher_dialog(voucher_string);
            }
        );
    },
};


function show_voucher_dialog(voucher_string) {
    const vouchers = voucher_string
        .split("||")
        .filter(Boolean);

    const rows = vouchers
        .map((voucher) => {
            const separator_index = voucher.indexOf("::");

            if (separator_index === -1) {
                return "";
            }

            const voucher_type = voucher.substring(
                0,
                separator_index
            );

            const voucher_no = voucher.substring(
                separator_index + 2
            );

            let route = "";

            if (voucher_type === "Stock Entry") {
                route = "stock-entry";
            } else if (voucher_type === "Purchase Receipt") {
                route = "purchase-receipt";
            } else {
                route = frappe.router.slug(voucher_type);
            }

            const url =
                `/app/${route}/${encodeURIComponent(voucher_no)}`;

            return `
                <li style="margin-bottom: 8px;">
                    <a
                        href="${url}"
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        ${frappe.utils.escape_html(voucher_no)}
                    </a>
                    <span class="text-muted">
                        (${frappe.utils.escape_html(voucher_type)})
                    </span>
                </li>
            `;
        })
        .join("");

    const dialog = new frappe.ui.Dialog({
        title: __("Contributing Vouchers"),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "voucher_list",
            },
        ],
        size: "small",
    });

    dialog.fields_dict.voucher_list.$wrapper.html(`
        <ul style="padding-left: 20px; margin-bottom: 0;">
            ${rows}
        </ul>
    `);

    dialog.show();
}