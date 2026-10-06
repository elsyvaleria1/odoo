/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog";
export class CustomerFacingQR extends Component {
    static template = "point_of_sale.CustomerFacingQR";
    static components = { Dialog };
    static props = {
        qrCode: t.string(),
        name: t.string(),
        amount: t.string(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.title = _t("Please scan the QR code with %s", this.props.name);
    }
}
