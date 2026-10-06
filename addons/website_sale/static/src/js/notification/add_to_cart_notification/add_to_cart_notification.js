/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { formatCurrency } from "@web/core/currency";

export class AddToCartNotification extends Component {
    static template = "website_sale.addToCartNotification";
    static props = {
        lines: t.array(
            t.object({
                id: t.number(),
                linked_line_id: t.number().optional(),
                image_url: t.string(),
                quantity: t.number(),
                uom_name: t.string().optional(),
                combination_name: t.string().optional(),
                name: t.string(),
                description: t.string().optional(),
                price_total: t.number(),
            }),
        ),
        currency_id: t.number(),
    };
    props = useProps(this.constructor.props);

    /**
     * @return {Object[]}
     */
    get mainLines() {
        return this.props.lines.filter((line) => !line.linked_line_id);
    }

    /**
     * @param {Number} lineId
     * @return {Object[]}
     */
    getLinkedLines(lineId) {
        return this.props.lines.filter((line) => line.linked_line_id === lineId);
    }

    /**
     * @param {Object} line
     * @return {String}
     */
    getFormattedPrice(line) {
        const linkedLines = this.getLinkedLines(line.id);
        const price = linkedLines.length
            ? linkedLines.reduce(
                  (price, linkedLine) => price + linkedLine.price_total,
                  0,
              )
            : line.price_total;
        return formatCurrency(price, this.props.currency_id);
    }
}
