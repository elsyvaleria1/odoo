/** @odoo-module native */
import { Component, markup, t, useProps } from "@odoo/owl";
import { SignRefusalDialog } from "@sign/dialogs/dialogs";
import { useSignContext } from "@sign/sign_context";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { useService } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";

export class SignableRequestControlPanel extends Component {
    static template = "sign.SignSignableRequestControlPanel";
    static components = {
        ControlPanel,
        Dropdown,
        DropdownItem,
    };
    static props = {
        signerStatus: t.object().optional(),
        goBackToKanban: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.signContext = useSignContext();
        this.controlPanelDisplay = {};
        this.action = useService("action");
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.signInfo = useService("signInfo");
    }

    refuseDocument() {
        this.dialog.add(SignRefusalDialog);
    }

    get markupSignerStatus() {
        return markup(this.props.signerStatus.innerHTML);
    }

    toggleEditBar() {
        this.signContext.editWhileSigningBus.trigger("toggleEditBar");
    }
}
