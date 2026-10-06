/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";
import { t } from "@odoo/owl";

export class ShadowOption extends BaseOptionComponent {
    static template = "html_builder.ShadowOption";
    static props = {
        setShadowModeAction: t.string().optional("setShadowMode"),
        setShadowAction: t.string().optional("setShadow"),
    };
}
