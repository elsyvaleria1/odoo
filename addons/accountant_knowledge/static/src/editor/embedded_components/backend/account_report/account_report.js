/** @odoo-module native */
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useViewModel } from "@web/model/model";

export class AccountReportComponent extends Component {
    static template = "accountant_knowledge.EmbeddedAccountReport";
    static props = { host: t.object(), name: t.string(), options: t.object() };
    props = useProps(this.constructor.props);
    setup() {
        this.model = useViewModel();
        this.actionService = useService("action");
    }
    /** @returns {Promise} */
    openAccountReport() {
        return this.actionService.doAction({
            type: "ir.actions.client",
            tag: "account_report",
            name: this.props.name,
            params: {
                ignore_session: true,
                options: this.props.options,
            },
            context: {
                html_element_host_id: this.props.host.dataset.oeId,
                article_id: this.model.root.resId,
                report_id: this.props.options.report_id,
            },
        });
    }
}

export const accountReportEmbedding = {
    name: "accountReport",
    Component: AccountReportComponent,
    getProps: (host) => ({
        ...getEmbeddedProps(host),
        host,
    }),
};
