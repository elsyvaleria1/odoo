/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";

export class CaptchaSubscribeOption extends BaseOptionComponent {
    static template = "website_mass_mailing.CaptchaSubscribeOption";
    static dependencies = ["captchaSubscribeOption"];

    setup() {
        super.setup();
        this.hasCaptchaLegal = this.dependencies.captchaSubscribeOption.hasCaptchaLegal;
    }
}
