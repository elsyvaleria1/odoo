/** @odoo-module native */
import { components, helpers } from "@odoo/o-spreadsheet";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useSpreadsheetEnv } from "@spreadsheet/hooks";
import { ModelSelector } from "@web/components/model_selector";

const { Section, TextInput } = components;
const uuidGenerator = new helpers.UuidGenerator();

export class NewPivotSidePanel extends Component {
    static template = "spreadsheet_edition.NewPivotSidePanel";
    static components = {
        TextInput,
        Section,
        ModelSelector,
    };
    static props = { onCloseSidePanel: t.function() };
    props = useProps(this.constructor.props);
    env = useSpreadsheetEnv();

    setup() {
        this.state = proxy({
            model: undefined,
        });
    }

    get isSaveAllowed() {
        return this.state.model;
    }

    onModelSelected(model) {
        this.state.model = model;
    }

    save() {
        const pivotId = uuidGenerator.smallUuid();
        this.env.model.dispatch("ADD_AND_INSERT_NEW_ODOO_PIVOT", {
            resModel: this.state.model.technical,
            name: this.state.model.label,
            pivotId,
        });
        this.env.openSidePanel("PivotSidePanel", {
            pivotId,
        });
    }
}
