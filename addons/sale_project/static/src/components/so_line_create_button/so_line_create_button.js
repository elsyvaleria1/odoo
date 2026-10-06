/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import {
    buildM2OFieldDescription,
    computeM2OProps,
    Many2One,
    Many2OneField,
} from "@web/fields/relational/many2one";
import { FormViewDialog } from "@web/views/view_dialogs";

export class SoLineCreateButton extends Component {
    static template = "sale_project.SoLineCreateButton";
    static components = { Many2One };
    static props = { ...Many2OneField.props };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.dialogService = useService("dialog");
    }

    openSalesOrderDialog() {
        const { context, record } = this.props;
        this.dialogService.add(FormViewDialog, {
            title: "Create Sales Order",
            resModel: "sale.order",
            context: {
                ...context,
                form_view_ref: context.so_form_view_ref,
                default_company_id: context.default_company_id || user.activeCompany.id,
                default_user_id: user.userId,
                hide_pdf_quote_builder: true,
            },
            onRecordSaved: async (rec) => {
                const service_line_id = await rec.model.orm.call(
                    "sale.order",
                    "get_first_service_line",
                    [rec.resId],
                );
                record.update({ sale_line_id: { id: service_line_id[0] } });
            },
        });
    }

    get m2oProps() {
        return computeM2OProps(this.props);
    }
}

registry.category("fields").add("so_line_create_button", {
    ...buildM2OFieldDescription(SoLineCreateButton),
});
