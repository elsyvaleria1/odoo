import { GeoengineRenderer } from "@geoengine/geoengine/geoengine_renderer";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(GeoengineRenderer.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
    },
    /**
     * @returns {boolean}
     */
    supportsTrailButton() {
        return this.props.model?.root?.resModel === "device.device";
    },

    async onViewTrailClicked() {
        if (!this.record) {
            console.warn("[GeoengineDeviceTrail] No record available");
            return;
        }

        const recordId = this.record.resId;
        if (!recordId) {
            console.warn("[GeoengineDeviceTrail] No record ID available");
            return;
        }

        try {
            const orm = this.orm;
            const actionService = this.action;

            const result = await orm.call("device.device", "action_view_today_trail", [
                [recordId],
            ]);

            if (result) {
                await actionService.doAction(result);
            }
        } catch (error) {
            console.error("[GeoengineDeviceTrail] Error:", error);
            if (this.notification) {
                this.notification.add(
                    error.data?.message ||
                        "Failed to generate trail. The device may not have GPS data for today.",
                    { type: "danger" },
                );
            }
        }
    },
});
