/** @odoo-module native */
import { QualityCheck } from "@mrp_workorder/mrp_display/mrp_record_line/quality_check";
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/ui/dialog";

export class IotPicturePreview extends Component {
    static components = { Dialog };
    static template = "mrp_workorder_iot.ImagePreviewDialog";
    static props = { src: t.string(), close: t.function() };
    props = useProps(this.constructor.props);
}

patch(QualityCheck.prototype, {
    setup() {
        super.setup();
        this.notification = useService("notification");
        this.iotHttpService = useService("iot_http");
    },
    get iotDevice() {
        return {
            iotBoxId: this.props.record.data.iot_box_id.id,
            deviceIdentifier: this.props.record.data.identifier,
        };
    },
    async clicked() {
        const { iotBoxId, deviceIdentifier } = this.iotDevice;
        if (this.type !== "picture" || !iotBoxId || !deviceIdentifier) {
            return super.clicked();
        }
        this.notification.add(_t("Capturing image..."));
        this.iotHttpService.action(
            iotBoxId,
            deviceIdentifier,
            {},
            this.iotUpdatePicture.bind(this),
            this._notifyFailure.bind(this),
        );
    },
    _notifyFailure() {
        this.notification.add(_t("Please check if the device is still connected."), {
            type: "danger",
        });
    },
    async iotUpdatePicture(data) {
        if (!data.result?.image) {
            return this._notifyFailure();
        }
        this.notification.add(_t("Image captured successfully"), { type: "success" });
        const imageBase64 = data.result?.image;
        await this.onFileUploaded({ data: imageBase64 });
        this.dialog.add(IotPicturePreview, { src: this.imageUrl });
    },
});
