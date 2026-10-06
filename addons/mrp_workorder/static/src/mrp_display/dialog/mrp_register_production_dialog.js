/** @odoo-module native */
import { proxy, t } from "@odoo/owl";
import { formatFieldFloat } from "@web/core/formatters";
import { useService } from "@web/core/utils/hooks";
import { FloatField } from "@web/fields/basic/float/float_field";
import { Many2ManyTagsField } from "@web/fields/relational/many2many_tags";
import { ConfirmationDialog } from "@web/ui/dialog";

export class MrpRegisterProductionDialog extends ConfirmationDialog {
    static template = "mrp_workorder.MrpRegisterProductionDialog";
    static props = {
        ...ConfirmationDialog.props,
        qtyToProduce: t.number().optional(),
        record: t.object(),
        reload: t.function(),
        workorderId: t.number().optional(),
    };
    static components = {
        ...ConfirmationDialog.components,
        FloatField,
        Many2ManyTagsField,
    };

    setup() {
        super.setup();
        if (this.props.qtyToProduce) {
            this.quantityToProduce = this.props.qtyToProduce;
        } else {
            this.quantityToProduce = this.props.record.data.product_qty;
        }
        this.formatFloat = formatFieldFloat;
        this.state = proxy({ disabled: false });
        if (
            ["lot", "serial"].includes(this.props.record.data.product_tracking) &&
            !this.props.record.data.trace_producing_ids.count
        ) {
            this.props.record.load();
        }
        this.actionService = useService("action");
    }

    async validate() {
        const record = this.props.record;
        this.state.disabled = true;
        await record.save();
        const resModel = this.props.workorderId ? "mrp.workorder" : "mrp.production";
        const resId = [this.props.workorderId || record.resId];
        await record.model.orm.call(resModel, "set_qty_producing", [resId]);
        await this.props.reload(record);
        this.props.close();
    }

    async actionGenerateSerial() {
        const action = await this.props.record.model.orm.call(
            this.props.record.resModel,
            "action_generate_serial",
            [this.props.record.resId],
        );
        if (action && typeof action === "object") {
            return this.actionService.doAction(action, {
                onClose: () => {
                    this.props.reload(this.props.record);
                },
            });
        }
        await this.props.reload(this.props.record);
    }

    async actionClearLotProducing() {
        await this.props.record.model.orm.call(
            this.props.record.resModel,
            "action_clear_lot_producing_ids",
            [this.props.record.resId],
        );
        await this.props.reload(this.props.record);
    }

    get lotInfo() {
        const { product_id, company_id } = this.props.record.data;
        return {
            name: "trace_producing_ids",
            record: this.props.record,
            context: {
                default_product_id: product_id.id,
                default_company_id: company_id.id,
            },
            domain: [
                "&",
                ["product_id", "=", product_id.id],
                "|",
                ["company_id", "=", false],
                ["company_id", "=", company_id.id],
            ],
        };
    }

    get qtyDoneInfo() {
        return {
            name: "qty_producing",
            record: this.props.record,
        };
    }
}
