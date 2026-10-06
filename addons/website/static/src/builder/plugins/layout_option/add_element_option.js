/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";
import { t } from "@odoo/owl";

export class AddElementOption extends BaseOptionComponent {
    static template = "website.AddElementOption";
    static props = { level: t.number().optional(0), applyTo: t.string().optional() };
}
