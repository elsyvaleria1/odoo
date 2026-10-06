/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";
import { t } from "@odoo/owl";

export class SpacingOption extends BaseOptionComponent {
    static template = "website.SpacingOption";
    static props = { level: t.number().optional(0), applyTo: t.string().optional() };
}
