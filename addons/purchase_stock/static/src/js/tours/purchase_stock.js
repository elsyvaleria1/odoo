/** @odoo-module native */
import PurchaseAdditionalTourSteps from "@purchase/js/tours/purchase_steps";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { stepUtils } from "@web_tour/tour_utils";

patch(PurchaseAdditionalTourSteps.prototype, {
    getPurchaseStockSteps() {
        return [
            {
                trigger: ".o-form-buttonbox button[name='action_view_picking']",
            },
            {
                trigger: ".o-form-buttonbox button[name='action_view_picking']",
                content: _t("Receive the ordered products."),
                tooltipPosition: "bottom",
                run: "click",
            },
            {
                trigger: ".o_statusbar_buttons button[name='button_validate']",
                content: _t("Validate the receipt of all ordered products."),
                tooltipPosition: "bottom",
                run: "click",
            },
            {
                isActive: ["auto"],
                trigger: ".o_statusbar_status .o_arrow_button_current:contains(Done)",
            },
            {
                trigger: ".o_back_button a, .breadcrumb-item:not('.active'):last",
                content: _t(
                    "Go back to the purchase order to generate the vendor bill.",
                ),
                tooltipPosition: "bottom",
                run: "click",
            },
            ...stepUtils.statusbarButtonsSteps(
                "Create Bill",
                _t("Bill the vendor for the received products."),
            ),
            {
                isActive: ["auto"],
                trigger:
                    ".modal .o_field_widget[name='advance_payment_method'] input[data-value='delivered']:checked",
            },
            {
                trigger: ".modal-footer button[name='create_invoices']",
                content: _t("Generate the draft vendor bill."),
                tooltipPosition: "bottom",
                run: "click",
            },
            {
                trigger: ".o_form_view .o_field_widget[name='invoice_line_ids']",
            },
        ];
    },
});

export default PurchaseAdditionalTourSteps;
