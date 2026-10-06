/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";
import { proxy, t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";

const log = makeLogger("website.builder.option.footer_template_option");

export class FooterTemplateOption extends BaseOptionComponent {
    static template = "website.FooterTemplateOption";
    static dependencies = ["footerOption"];
    static selector = "#wrapwrap > footer";
    static editableOnly = false;
    static groups = ["website.group_website_designer"];

    setup() {
        super.setup();
        useLifecycleLog(log);
        this.footerTemplates = proxy(
            this.dependencies.footerOption.getFooterTemplates(),
        );
    }
}

export class FooterTemplateChoice extends BaseOptionComponent {
    static template = "website.FooterTemplateChoice";
    static props = {
        title: t.string(),
        view: t.string(),
        varName: t.string(),
        imgSrc: t.string(),
    };
}
