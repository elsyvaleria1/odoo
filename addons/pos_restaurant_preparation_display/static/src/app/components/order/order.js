/** @odoo-module native */
import { Order } from "@pos_enterprise/app/components/order/order";
import { getPreparationDisplayColor } from "@web/core/colors/colors";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { patch } from "@web/core/utils/patch";
patch(Order.prototype, {
    setup() {
        super.setup();
        this.didMount = false;
        useLayoutEffect(
            (isPending) => {
                if (!this.didMount) {
                    this.didMount = true;
                    return;
                }
                if (!isPending) {
                    this._updateDuration();
                }
            },
            () => [this.isPending],
        );
    },
    get isPending() {
        const course = this.order.pos_course_id;
        return this.isInFirstStage() && course && !course.fired;
    },
    isInFirstStage() {
        return (
            this.prepDisplay.data.models["pos.prep.stage"].getFirst().id ===
            this.props.order.stage.id
        );
    },
    _getOrderDuration() {
        const course = this.order.pos_course_id;
        if (this.isInFirstStage() && course?.fired && course?.fired_date) {
            return this.order.getDurationSinceFireDate();
        }
        return super._getOrderDuration();
    },
    get cardColor() {
        const cardColor = super.cardColor;
        const tableId = this.order.pos_order_id.table_id?.id;
        let tableOrdersInStage = [];

        if (tableId && this.prepDisplay.tables[tableId].length) {
            const tableOrders = this.prepDisplay.tables[tableId];
            tableOrdersInStage = tableOrders.filter(
                (stageId) => stageId === this.props.order.stage.id,
            );

            if (this.prepDisplay.selectedStageId === 0) {
                tableOrdersInStage = tableOrders;
            }
        }

        return tableOrdersInStage.length > 1
            ? getPreparationDisplayColor(tableId)
            : cardColor;
    },
});
