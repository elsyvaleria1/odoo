import { registry } from "@web/core/registry";

const TAX_ITEM = ".o-autocomplete--dropdown-item:not(.o_m2o_dropdown_option)";
const COMPLETE_MENU = `.o-autocomplete--dropdown-menu:has(${TAX_ITEM}):not(:has(${TAX_ITEM}:not(:contains(TAXPICK))))`;

function taxPickerSteps(offered, hidden) {
    return [
        {
            content: "Open the optional columns of the lines",
            trigger:
                ".o_field_one2many[name=line_ids] .o_optional_columns_dropdown_toggle",
            run: "click",
        },
        {
            content: "Show the taxes column unless it is already shown",
            trigger: '.o-dropdown-item input[name="tax_ids"]',
            run() {
                if (!this.anchor.checked) {
                    this.anchor.click();
                }
            },
        },
        {
            content: "Close the optional columns",
            trigger:
                ".o_field_one2many[name=line_ids] .o_optional_columns_dropdown_toggle",
            run: "click",
        },
        {
            content: "Open the taxes of the first line",
            trigger:
                ".o_field_one2many[name=line_ids] .o_data_row:first td[name=tax_ids]",
            run: "click",
        },
        {
            trigger:
                ".o_data_row.o_selected_row td[name=tax_ids] .o-autocomplete--input",
            run: "edit TAXPICK",
        },
        {
            content: "Wait for the search of the full prefix",
            trigger: COMPLETE_MENU,
        },
        {
            content: `The picker offers ${offered}`,
            trigger: `${COMPLETE_MENU} ${TAX_ITEM}:contains(${offered})`,
        },
        {
            content: `The picker does not offer ${hidden}`,
            trigger: `${COMPLETE_MENU}:not(:has(${TAX_ITEM}:contains(${hidden})))`,
        },
    ];
}

registry
    .category("web_tour.tours")
    .add("sale_order_line_tax_picker_foreign_vat", {
        steps: () => taxPickerSteps("TAXPICK DE", "TAXPICK HOME"),
    })
    .add("sale_order_line_tax_picker_domestic", {
        steps: () => taxPickerSteps("TAXPICK HOME", "TAXPICK DE"),
    });
