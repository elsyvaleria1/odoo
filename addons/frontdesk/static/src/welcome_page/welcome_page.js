/** @odoo-module native */
import { Component, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { now, TIME_SIMPLE, toLocaleString } from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";

export class WelcomePage extends Component {
    static template = "frontdesk.WelcomePage";
    static props = {
        companyName: t.string(),
        currentLang: t.string(),
        langs: t.or([t.object(), t.boolean()]),
        onChangeLang: t.function(),
        token: t.string(),
        resetData: t.function(),
        showScreen: t.function(),
        stationInfo: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ today: this.getCurrentTime(), qrCode: false });
        this.timeInterval = setInterval(
            () => (this.state.today = this.getCurrentTime()),
            1000,
        );
        this.props.resetData();
        // Make the qr code only when self_check_in field is true from backend.
        if (this.props.stationInfo.self_check_in) {
            this._getQrCodeData();
            this.qrCodeInterval = setInterval(() => this._getQrCodeData(), 3600000); // 1 hour
        }
        onWillUnmount(() => {
            clearInterval(this.timeInterval);
            if (this.props.stationInfo.self_check_in) {
                clearInterval(this.qrCodeInterval);
            }
        });
    }

    getCurrentTime() {
        return toLocaleString(now(), TIME_SIMPLE);
    }

    /**
     * @private
     */
    async _getQrCodeData() {
        const response = await rpc(
            `/kiosk/${this.props.stationInfo.id}/get_tmp_code/${this.props.token}`,
        );
        const token = encodeURIComponent(response[0] + response[1]);
        this.state.qrCode = await this._makeQrCodeData(
            `${window.location.origin}/kiosk/${this.props.stationInfo.id}/mobile/${token}`,
        );
    }

    /**
     * @private
     */
    async _makeQrCodeData(url) {
        const { BrowserQRCodeSvgWriter } = await import("zxing-library");
        const codeWriter = new BrowserQRCodeSvgWriter();
        const qrCodeSVG = new XMLSerializer().serializeToString(
            codeWriter.write(url, 250, 250),
        );
        return (
            "data:image/svg+xml;base64," +
            new TextEncoder().encode(qrCodeSVG).toBase64()
        );
    }
}

registry.category("frontdesk_screens").add("WelcomePage", WelcomePage);
