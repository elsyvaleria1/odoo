/** @odoo-module native */
import { Component, markup, onMounted, t, useProps } from "@odoo/owl";
import { formatMonetary } from "@web/core/formatters";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { Dialog } from "@web/ui/dialog";

export class ProductMatrixDialog extends Component {
    static template = "product_matrix.dialog";
    static props = {
        header: t.array(),
        rows: t.array(),
        editedCellAttributes: t.string(),
        product_template_id: t.number(),
        record: t.object(),
        close: t.function(),
    };
    static components = { Dialog };
    props = useProps(this.constructor.props);

    setup() {
        this.size = "xl";

        const productMatrixRef = (this.productMatrixRef = elementRef());
        useHotkey("enter", () => this._onConfirm(), {
            bypassEditableProtection: true,
            area: () => productMatrixRef.el,
        });

        onMounted(() => {
            if (this.props.editedCellAttributes.length) {
                const inputs = document.getElementsByClassName("o_matrix_input");
                const relevantInput = Array.from(inputs).filter(
                    (matrixInput) =>
                        matrixInput.attributes.ptav_ids.nodeValue ===
                        this.props.editedCellAttributes,
                )[0];
                if (relevantInput) {
                    relevantInput.select();
                } else {
                    inputs[0].select();
                }
            } else {
                document.getElementsByClassName("o_matrix_input")[0].select();
            }
        });
    }

    _format({ price, currency_id }) {
        if (!price) {
            return "";
        }
        const sign = price < 0 ? "-" : "+";
        const formatted = formatMonetary(Math.abs(price), {
            currencyId: currency_id,
        });
        return markup(`&nbsp;${sign}&nbsp;${formatted}&nbsp;`);
    }

    _onConfirm() {
        const inputs = document.getElementsByClassName("o_matrix_input");
        const matrixChanges = [];
        for (const matrixInput of inputs) {
            if (
                matrixInput.value &&
                matrixInput.value !== matrixInput.attributes.value.nodeValue
            ) {
                matrixChanges.push({
                    qty: parseFloat(matrixInput.value),
                    ptav_ids: matrixInput.attributes.ptav_ids.nodeValue
                        .split(",")
                        .map((id) => parseInt(id)),
                });
            }
        }
        if (matrixChanges.length > 0) {
            this.props.record.update({
                grid: JSON.stringify({
                    changes: matrixChanges,
                    product_template_id: this.props.product_template_id,
                }),
                grid_update: true,
            });
        }
        this.props.close();
    }
}
