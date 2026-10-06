/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { IntegerField } from "@web/fields/basic/integer/integer_field";
import { Many2OneField } from "@web/fields/relational/many2one";
import { X2ManyField, x2ManyField } from "@web/fields/relational/x2many";

export class SignerX2Many extends X2ManyField {
    static template = "sign.SignerX2Many";
    static components = {
        ...X2ManyField.components,
        Many2OneField,
        IntegerField,
    };

    static props = { ...X2ManyField.props };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    get partnerIdFieldInfo() {
        return {
            name: "partner_id",
            forceSave: true,
            additionalProps: {
                readonly: false,
                placeholder: _t("Type a name or email..."),
                context: { force_email: true, show_email: true },
            },
        };
    }

    get shouldShowOrder() {
        return this.props.record.data["set_sign_order"];
    }
}

export const signerX2Many = {
    component: SignerX2Many,
    displayName: _t("Signer One 2 Many"),
    additionalClasses: ["o_required_modifier"],
    supportedTypes: ["one2many"],
    relatedFields: () => [
        {
            name: "role_id",
            type: "many2one",
            relation: "sign.item.role",
            readonly: false,
        },
        {
            name: "partner_id",
            type: "many2one",
            relation: "res.partner",
            readonly: false,
        },
        { name: "mail_sent_order", type: "integer", readonly: false },
    ],
    fieldDependencies: [{ name: "set_sign_order", type: "boolean" }],
    extractProps: x2ManyField.extractProps,
};

registry.category("fields").add("signer_x2many", signerX2Many);
