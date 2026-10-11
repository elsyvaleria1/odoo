/** @odoo-module native */
import { useBus, useEventBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { GraphController, GraphModel } from "@web/views/graph";

patch(GraphController.prototype, {
    setup() {
        super.setup(...arguments);
        this.bus = useEventBus();
        useBus(this.bus, "APPLY_AI_ADJUST_MODEL", async ({ detail }) => {
            const { measures, mode, order, stacked, cumulated } = detail;
            if (this.model instanceof GraphModel) {
                const defaultMetaData = this.model._buildMetaData();
                const metaData = this.model._buildMetaData({
                    measures,
                    mode: mode ?? defaultMetaData.mode,
                    order: order ?? defaultMetaData.order,
                    stacked: stacked ?? defaultMetaData.stacked,
                    cumulated: cumulated ?? defaultMetaData.stacked,
                });
                const validMeasures = measures.filter((m) => m in metaData.measures);
                const activeMeasures = metaData.activeMeasures || [];
                const measuresToActivate = validMeasures.filter(
                    (m) => !activeMeasures.includes(m),
                );
                const measure = measuresToActivate[0] ?? metaData.measure;
                if (measure) {
                    await this.model.updateMetaData({ measure });
                }
                this.model.updateMetaData({
                    mode: mode ?? metaData.mode,
                    order: order ?? metaData.order,
                    stacked: stacked ?? metaData.stacked,
                    cumulated: cumulated ?? metaData.cumulated,
                });
            }
        });
    },
});
