/** @odoo-module native */
import { serializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { redirect } from "@web/core/utils/urls";
import { Interaction } from "@web/public/interaction";
import { RentingMixin } from "@website_sale_renting/js/renting_mixin";

export class RentalSearchSnippet extends Interaction {
    static selector = ".s_rental_search";
    dynamicContent = {
        ".s_rental_search_btn": { "t-on-click": this.onClickRentalSearchButton },
        ".o_website_sale_daterange_picker": {
            "t-on-toggle_search_btn": this.onToggleSearchBtn,
        },
    };

    onToggleSearchBtn(ev) {
        ev.currentTarget.querySelector(".s_rental_search_btn").disabled = Boolean(
            ev.detail,
        );
    }

    onClickRentalSearchButton() {
        const startInput = this.el.querySelector("input[name=renting_start_date]");
        const endInput = this.el.querySelector("input[name=renting_end_date]");
        this.searchRentals({
            detail: {
                startDate: this._parseRentingDate(startInput.value),
                endDate: this._parseRentingDate(endInput.value),
            },
        });
    }

    /**
     * @param {CustomEvent} event
     */
    searchRentals(event) {
        const { startDate, endDate } = event.detail;
        const searchParams = new URLSearchParams();
        if (startDate && endDate) {
            searchParams.append("start_date", serializeDateTime(startDate));
            searchParams.append("end_date", serializeDateTime(endDate));
        }
        const productAttributeId = this.el.querySelector(
            ".product_attribute_search_rental_name",
        ).id;

        const productAttributeValueId = this.el.querySelector(
            ".s_rental_search_select",
        ).value;
        if (productAttributeValueId) {
            searchParams.append(
                "attribute_values",
                `${productAttributeId}-${productAttributeValueId}`,
            );
        }
        redirect(`/shop?${searchParams.toString()}`);
    }
}

Object.assign(RentalSearchSnippet.prototype, RentingMixin);

registry
    .category("public.interactions")
    .add("website_sale_renting.rental_search_snippet", RentalSearchSnippet);
