/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";
import { markup, t } from "@odoo/owl";

export class ImportedFooterTemplateChoice extends BaseOptionComponent {
    static template = "website_generator.ImportedFooterTemplateChoice";
    static props = {
        title: t.string(),
        view: t.string(),
        varName: t.string(),
        imgSrc: t.string(),
    };
    setup() {
        this.label = markup`<Img attrs="{ style: 'width: 100%;' }" src="${this.props.imgSrc}"/>`;
    }
}
