/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

registry.category("website.form_editor_actions").add("create_ticket", {
    formFields: [
        {
            type: "char",
            required: true,
            name: "partner_name",
            fillWith: "name",
            string: _t("Full Name"),
        },
        {
            type: "tel",
            name: "phone",
            fillWith: "phone",
            string: _t("Phone Number"),
        },
        {
            type: "email",
            required: true,
            name: "partner_email",
            fillWith: "email",
            string: _t("Email Address"),
        },
        {
            type: "char",
            fillWith: "commercial_company_name",
            name: "partner_company_name",
            string: _t("Company Name"),
        },
        {
            type: "char",
            modelRequired: true,
            name: "name",
            string: _t("Message Subject"),
        },
        {
            type: "text",
            required: true,
            name: "description",
            string: _t("Ask Your Question"),
        },
        {
            type: "binary",
            custom: true,
            name: _t("Attach File"),
        },
    ],
    fields: [
        {
            name: "team_id",
            type: "many2one",
            relation: "team.team",
            domain: [["use_helpdesk", "=", true]],
            string: _t("Helpdesk Team"),
        },
    ],
    successPage: "/your-ticket-has-been-submitted",
});
