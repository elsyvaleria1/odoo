/** @odoo-module native */
import { Component, markup, t, useProps } from "@odoo/owl";
import { formatFieldFloat } from "@web/core/formatters";
import { formatDate, today as todayDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

/**
 * @param {Temporal.ZonedDateTime} value
 * @param {number} days
 */
function addFractionalDays(value, days) {
    const wholeDays = Math.trunc(days);
    return value
        .add({ days: wholeDays })
        .add({ milliseconds: Math.round((days - wholeDays) * 86400000) });
}

export class ForecastedHeader extends Component {
    static template = "stock.ForecastedHeader";
    static props = { docs: t.object(), openView: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this._formatFloat = (num) =>
            formatFieldFloat(num, { digits: [false, this.props.docs.precision] });
        this.leadTimeData = this._computeLeadTime();
    }

    async _onClickInventory() {
        const productIds = this.props.docs.product_variants_ids;
        const action = await this.orm.call("product.product", "action_view_quants", [
            productIds,
        ]);
        if (action.help) {
            action.help = markup(action.help);
        }
        return this.action.doAction(action);
    }

    get products() {
        return this.props.docs.product;
    }

    get leadTime() {
        return this.leadTimeData;
    }

    _computeLeadTime() {
        const productsArray = Object.values(this.products || {});
        if (!productsArray.length) {
            return null;
        }
        const product = productsArray.reduce((minProduct, p) => {
            if (
                !minProduct ||
                (p.leadtime &&
                    p.leadtime.total_delay <
                        (minProduct.leadtime?.total_delay ?? Infinity))
            ) {
                return p;
            }
            return minProduct;
        }, null);
        if (!product?.leadtime) {
            return null;
        }
        const today = todayDate();
        return {
            ...product.leadtime,
            today: formatDate(today),
            earliestPossibleArrival: formatDate(
                addFractionalDays(today, product.leadtime.total_delay),
            ),
        };
    }

    get leadTimeShort() {
        const { total_delay, earliestPossibleArrival } = this.leadTime;
        if (total_delay === 0) {
            return _t("%(delay)s day(s)", { delay: total_delay });
        }
        return _t("%(delay)s day(s) (%(date)s)", {
            delay: total_delay,
            date: earliestPossibleArrival,
        });
    }

    _total(field) {
        return Object.values(this.products).reduce(
            (sum, product) => sum + product[field],
            0,
        );
    }

    get quantityOnHand() {
        return this._total("quantity_on_hand");
    }

    get incomingQty() {
        return this._total("qty_incoming");
    }

    get outgoingQty() {
        return this._total("qty_outgoing");
    }

    get virtualAvailable() {
        return this._total("qty_available_virtual");
    }

    get uom() {
        return Object.values(this.products)[0]?.uom ?? "";
    }

    toJsonString(obj) {
        return JSON.stringify(obj);
    }
}
