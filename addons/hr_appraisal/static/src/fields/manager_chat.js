/** @odoo-module native */
import { useOpenChat } from "@mail/core/web/open_chat_hook";
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets";

export class AppraisalManagerChat extends Component {
    static template = "hr_appraisal.ManagerChat";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.openChat = useOpenChat("hr.employee");
    }
}

export const appraisalManagerChat = {
    component: AppraisalManagerChat,
};
registry.category("view_widgets").add("appraisal_manager_chat", appraisalManagerChat);
