/** @odoo-module native */
import { HostManualSelection } from "@frontdesk/host_page/host_manual_selection";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class HostPage extends Component {
    static template = "frontdesk.HostPage";
    static components = { HostManualSelection };
    static props = {
        setHostData: t.function(),
        showScreen: t.function(),
        stationId: t.number(),
        token: t.string(),
        theme: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            showManualSelection: false,
            hostName: "",
        });
    }

    /** @private */
    _onConfirm() {
        this.props.setHostData(this.host);
        this.props.showScreen("RegisterPage");
    }

    /**
     * @param {object | null} host
     */
    selectedHost(host) {
        this.host = host;
        this.state.hostName = host?.display_name ?? "";
        this.state.showManualSelection = false;
    }

    showManualSelection() {
        this.state.showManualSelection = true;
    }

    goBackFromManualSelection() {
        this.state.showManualSelection = false;
    }
}

registry.category("frontdesk_screens").add("HostPage", HostPage);
