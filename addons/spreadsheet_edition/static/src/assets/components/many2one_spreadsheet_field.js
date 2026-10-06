/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    buildM2OFieldDescription,
    computeM2OProps,
    Many2One,
    Many2OneField,
} from "@web/fields/relational/many2one";
import { useViewModel } from "@web/model/model";

export class Many2OneSpreadsheetField extends Component {
    static template = "spreadsheet_edition.Many2OneSpreadsheetField";
    static components = { Many2One };
    static props = { ...Many2OneField.props };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.viewModel = useViewModel();
    }

    get m2oProps() {
        return {
            ...computeM2OProps(this.props),
            createAction: (params) => this.openSpreadsheet(params),
        };
    }

    async openSpreadsheet({ context }) {
        const relation = this.props.record.fields[this.props.name].relation;
        const action = await this.orm.call(
            relation,
            "action_view_new_spreadsheet",
            [],
            {
                context,
            },
        );
        this.props.record.update({
            [this.props.name]: { id: action.params.spreadsheet_id },
        });
        await this.viewModel.root.save();
        await this.action.doAction(action);
    }
}

registry.category("fields").add("many2one_spreadsheet", {
    ...buildM2OFieldDescription(Many2OneSpreadsheetField),
});
