/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

import { SaleActionHelperDialog } from "./sale_action_helper_dialog.js";

export class SaleActionHelper extends Component {
    static template = "sale.SaleActionHelper";
    static props = { noContentHelp: t.string() };
    props = useProps(this.constructor.props);

    setup() {
        this.dialogService = useService("dialog");
    }

    openVideoPreview() {
        this.dialogService.add(SaleActionHelperDialog, {
            url: "https://www.youtube.com/embed/N4zw-2t6spk?autoplay=1",
        });
    }
}
