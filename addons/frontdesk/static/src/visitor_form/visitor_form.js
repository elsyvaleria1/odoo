/** @odoo-module native */
import { Component, onMounted, onWillUnmount, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";

export class VisitorForm extends Component {
    static template = "frontdesk.VisitorForm";
    static props = {
        clearUpdatePlannedVisitors: t.function(),
        currentComponent: t.string(),
        currentLang: t.string(),
        isMobile: t.boolean(),
        isPlannedVisitors: t.boolean(),
        langs: t.or([t.object(), t.boolean()]),
        onChangeLang: t.function(),
        setVisitorData: t.function(),
        showScreen: t.function(),
        stationInfo: t.object(),
        updatePlannedVisitors: t.function(),
        visitorData: t.or([t.object(), t.boolean()]),
        theme: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.inputNameRef = elementRef();
        this.inputPhoneRef = elementRef();
        this.inputEmailRef = elementRef();
        this.inputCompanyRef = elementRef();
        this.props.updatePlannedVisitors();
        onMounted(() => {
            this.inputNameRef.el.focus();
        });
        onWillUnmount(() => {
            this.props.clearUpdatePlannedVisitors();
        });
    }

    /**
     * @private
     */
    _onSubmit() {
        this.props.setVisitorData(
            this.inputNameRef.el.value,
            this.inputPhoneRef.el?.value || false,
            this.inputEmailRef.el?.value || false,
            this.inputCompanyRef.el?.value || false,
        );
        // Show the HostPage component, if the host_selection field is true from the backend
        this.props.stationInfo.host_selection
            ? this.props.showScreen("HostPage")
            : this.props.showScreen("RegisterPage");
    }
}

registry.category("frontdesk_screens").add("VisitorForm", VisitorForm);
