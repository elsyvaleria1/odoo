import { models } from "@web/../tests/web_test_helpers";

export class PosOrderLine extends models.ServerModel {
    _name = "pos.order.line";

    read_for_refund(ids, fieldNames) {
        const refundIds = this.search([["refunded_orderline_id", "in", ids]]);
        const refunds = this.read(
            refundIds,
            ["refunded_orderline_id", "order_id", "qty"],
            false,
        );
        const orders = this.env["pos.order"].read(
            [...new Set(refunds.map((refund) => refund.order_id))],
            ["state", "uuid", "pos_reference", "name", "config_id"],
            false,
        );
        const orderById = Object.fromEntries(orders.map((order) => [order.id, order]));
        return {
            lines: this.read(ids, fieldNames, false),
            draft_refunds: refunds
                .filter((refund) => orderById[refund.order_id]?.state === "draft")
                .map((refund) => {
                    const order = orderById[refund.order_id];
                    return {
                        line_id: refund.refunded_orderline_id,
                        order_uuid: order.uuid,
                        order: order.pos_reference || order.name,
                        till: this.env["pos.config"].read(
                            [order.config_id],
                            ["name"],
                        )[0]?.name,
                        qty: -refund.qty,
                    };
                }),
        };
    }

    _load_pos_data_fields() {
        return [
            "qty",
            "attribute_value_ids",
            "custom_attribute_value_ids",
            "price_unit",
            "uuid",
            "price_subtotal",
            "price_subtotal_incl",
            "order_id",
            "note",
            "price_type",
            "product_id",
            "discount",
            "tax_ids",
            "pack_lot_ids",
            "customer_note",
            "refunded_qty",
            "price_extra",
            "full_product_name",
            "refunded_orderline_id",
            "combo_parent_id",
            "combo_line_ids",
            "combo_item_id",
            "combo_qty_per_parent",
            "refund_orderline_ids",
            "extra_tax_data",
            "discount_barcode",
            "write_date",
        ];
    }
}
