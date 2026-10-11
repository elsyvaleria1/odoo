/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { roundDecimals } from "@web/core/utils/format/numbers";
import { useService } from "@web/core/utils/hooks";
import { useRecordObserver } from "@web/fields/hooks/record_observer";
import { standardWidgetProps } from "@web/views/widgets";

export class Digipad extends Component {
    static template = "stock_barcode.DigipadTemplate";
    static props = {
        ...standardWidgetProps,
        fieldToEdit: t.string(),
        fulfilledAt: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        const { data } = this.props.record;
        const context = this.props.record.evalContext.context;
        this.value = String(data[this.props.fieldToEdit]);
        this.fulfillQuantity =
            this.props.fulfilledAt && !context.hide_qty_to_count
                ? data[this.props.fulfilledAt]
                : 0;
        if (context.force_fullfil_quantity) {
            this.fulfillQuantity = context.force_fullfil_quantity;
        }
        const field = this.props.record.model.config.fields[this.props.fieldToEdit];
        this.precision = field.digits[1];
        this.productId = this.props.record.data.product_id.id;
        this.state = proxy({
            packagingButtons: [],
        });
        useRecordObserver(async (record) => {
            if (this.productId !== record.data.product_id.id) {
                this.productId = record.data.product_id.id;
                await this._fetchPackagingButtons();
            }
        });
        onWillStart(() => this._fetchPackagingButtons());
    }

    get quantity() {
        return this.props.record.data[this.props.fieldToEdit] || 0;
    }

    get changes() {
        return { [this.props.fieldToEdit]: Number(this.value) };
    }

    get quantityToFulfill() {
        if (!this.fulfillQuantity) {
            return 0;
        }
        const record = this.props.record.data;
        const currentQty = record[this.props.fieldToEdit];

        return roundDecimals(this.fulfillQuantity - currentQty, this.precision);
    }

    get buttonContainerClass() {
        return this.fulfillQuantity ? "col-3" : "col-4";
    }

    get buttonFulfillClass() {
        if (this.quantityToFulfill > 0) {
            return "btn-success";
        } else if (this.quantityToFulfill < 0) {
            return "btn-warning";
        }
        return "btn-secondary text-success";
    }

    /**
     * The quantity typed in the field, which may not be in the record yet.
     * @private
     */
    _typedQuantity() {
        const input = document.querySelector(
            `div[name="${this.props.fieldToEdit}"] input`,
        );
        return input ? Number(input.value || 0) : this.quantity;
    }

    /**
     * @private
     * @param {number} quantity
     */
    _setQuantity(quantity) {
        this.value = quantity.toFixed(this.precision);
        if (parseFloat(this.value) % 1 === 0) {
            this.value = String(Math.floor(parseFloat(this.value)));
        }
        return this.props.record.update(this.changes);
    }

    /**
     * Increments the field value by the interval amount (1 by default).
     * @private
     * @param {integer} [interval=1]
     */
    _increment(interval = 1, enforceQuantity = false) {
        const quantity = enforceQuantity
            ? interval
            : Math.max(this._typedQuantity() + interval, 0);
        return this._setQuantity(quantity);
    }

    /**
     * Search for the product's packaging buttons.
     * @private
     * @returns {Promise}
     */
    async _fetchPackagingButtons() {
        const record = this.props.record.data;
        this.productUom = (
            await this.orm.searchRead(
                "uom.uom",
                [["id", "=", record.product_uom_id?.id]],
                ["factor"],
            )
        )?.[0];
        if (record.product_id.id) {
            let domain = [["id", "=", record.product_id.id]];
            const product_uoms = await this.orm.searchRead("product.product", domain, [
                "uom_ids",
            ]);
            if (product_uoms.length === 0) {
                return;
            }
            domain = [["id", "in", product_uoms[0].uom_ids]];
            if (this.quantityToFulfill) {
                domain.push(["factor", "<=", this.quantityToFulfill]);
            }
            this.state.packagingButtons = await this.orm.searchRead(
                "uom.uom",
                domain,
                ["name", "factor", "package_type_id"],
                { limit: 2 },
            );
        } else {
            this.state.packagingButtons = [];
        }
    }

    /**
     * Resets the field value to 0.
     * @private
     */
    erase() {
        return this._setQuantity(0);
    }

    increment() {
        return this._increment();
    }

    decrement() {
        return this._increment(-1);
    }

    /**
     * Sets the field value to the fulfill quantity.
     * @private
     */
    fulfill() {
        return this._setQuantity(this.fulfillQuantity);
    }
}

export const digipad = {
    component: Digipad,
    extractProps: ({ attrs }) => ({
        fieldToEdit: attrs.field_to_edit,
        fulfilledAt: attrs.fulfilled_at,
    }),
};
registry.category("view_widgets").add("digipad", digipad);
