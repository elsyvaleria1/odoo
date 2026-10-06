/** @odoo-module native */
import { Component, onWillStart, onWillUnmount, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";

import { useInactivity } from "../use_inactivity.js";

export class RegisterPage extends Component {
    static template = "frontdesk.RegisterPage";
    static props = {
        createVisitor: t.function(),
        hostData: t.any().optional(),
        isDrinkVisible: t.boolean(),
        isMobile: t.boolean(),
        onClose: t.function(),
        plannedVisitorData: t.any().optional(),
        showScreen: t.function(),
        theme: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        if (!this.props.isMobile) {
            useInactivity(() => this.props.onClose(), 15000);
        }

        onWillStart(async () => {
            if (!this.props.plannedVisitorData) {
                // Check if a visitor has already been created
                const visitorCreated = sessionStorage.getItem("visitorCreated");
                if (!visitorCreated) {
                    await this.props.createVisitor();
                    if (this.props.isMobile) {
                        // Set the flag in sessionStorage
                        sessionStorage.setItem("visitorCreated", "true");
                    }
                }
            }
        });

        onWillUnmount(() => {
            if (this.props.isMobile) {
                // Clear the visitorCreated flag
                sessionStorage.removeItem("visitorCreated");
            }
        });
    }
}

registry.category("frontdesk_screens").add("RegisterPage", RegisterPage);
