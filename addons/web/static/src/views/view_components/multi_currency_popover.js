// @ts-check
/** @odoo-module native */

import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { getCurrency, getCurrencyRates } from "@web/core/currency";
import { formatMonetary } from "@web/core/formatters";
import { toLocaleDateString } from "@web/core/l10n/dates";
import { user } from "@web/core/user";
import { elementRef } from "@web/core/utils/element_ref";
import { useMountedListener } from "@web/core/utils/hooks";

export class MultiCurrencyPopover extends Component {
    static template = "web.MultiCurrencyPopover";
    static props = {
        close: t.function(),
        currencyIds: t.array(),
        target: t.instanceOf(HTMLElement),
        value: t.number(),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref} */
    rootRef;
    /** @type {{ rates: Record<number, { toCompanyRate: number, date: any }> | null }} */
    state;

    setup() {
        this.rootRef = elementRef();
        this.defaultCurrency = user.activeCompany?.currency_id;
        this.state = proxy({ rates: null });
        onWillStart(async () => {
            this.state.rates = await getCurrencyRates();
        });
        useMountedListener(window, "mouseover", (ev) => {
            const popoverEl = this.rootRef.el;
            const target = /** @type {Node} */ (ev.target);
            if (
                popoverEl &&
                !this.props.target.contains(target) &&
                !popoverEl.contains(target)
            ) {
                this.props.close();
            }
        });
    }

    /** @returns {Array<Object>} */
    get currencies() {
        const rates = this.state.rates;
        if (!rates) {
            return [];
        }
        return this.props.currencyIds.reduce((currencies, currencyId) => {
            const rateInfo = rates[currencyId];
            if (currencyId && currencyId !== this.defaultCurrency && rateInfo) {
                currencies.push({
                    ...getCurrency(currencyId),
                    id: currencyId,
                    toCompanyRate: rateInfo.toCompanyRate,
                    date: toLocaleDateString(rateInfo.date),
                    value: this.props.value / rateInfo.toCompanyRate,
                });
            }
            return currencies;
        }, []);
    }

    /**
     * @param {number} value
     * @param {number} currencyId
     * @returns {string}
     */
    formatedValue(value, currencyId) {
        return formatMonetary(value, { currencyId });
    }
}
