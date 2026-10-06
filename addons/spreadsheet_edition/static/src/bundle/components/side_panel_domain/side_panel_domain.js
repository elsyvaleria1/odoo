/** @odoo-module native */
import { components } from "@odoo/o-spreadsheet";
import { Component, t, useProps } from "@odoo/owl";
import { DomainSelector } from "@web/components/domain_selector";
import { DomainSelectorDialog } from "@web/components/domain_selector_dialog";
import { useDebugMode } from "@web/core/debug/debug_context";
import { Domain } from "@web/core/domain";
import { useService } from "@web/core/utils/hooks";

const { Section } = components;

export class SidePanelDomain extends Component {
    static template = "spreadsheet_edition.SidePanelDomain";
    static components = {
        DomainSelector,
        Section,
    };
    static props = {
        resModel: t.string(),
        domain: t.or([t.instanceOf(Domain), t.string(), t.array()]),
        onUpdate: t.function(),
    };
    props = useProps(this.constructor.props);

    getStringifiedDomain() {
        return new Domain(this.props.domain).toString();
    }

    setup() {
        this.debug = useDebugMode();
        this.dialog = useService("dialog");
    }

    openDomainEdition() {
        this.dialog.add(DomainSelectorDialog, {
            resModel: this.props.resModel,
            domain: this.getStringifiedDomain(),
            isDebugMode: !!this.debug,
            onConfirm: (domain) => {
                this.props.onUpdate(new Domain(domain).toJson());
            },
        });
    }
}
