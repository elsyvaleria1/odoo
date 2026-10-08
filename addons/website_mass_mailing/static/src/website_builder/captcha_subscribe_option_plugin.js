/** @odoo-module native */
import { Captcha } from "@captcha/captcha";
import { BuilderAction } from "@html_builder/core/builder_action";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { renderToElement } from "@web/core/utils/render";

class CaptchaSubscribeOptionPlugin extends Plugin {
    static id = "captchaSubscribeOption";
    static shared = ["hasCaptchaLegal"];
    resources = {
        builder_actions: {
            ToggleCaptchaLegalAction,
        },
    };

    hasCaptchaLegal() {
        return !!new Captcha().legalTemplate;
    }
}

export class ToggleCaptchaLegalAction extends BuilderAction {
    static id = "toggleCaptchaLegal";
    apply({ editingElement }) {
        editingElement.appendChild(
            renderToElement("captcha.legal_terms", {
                legalTemplate: new Captcha().legalTemplate,
            }),
        );
    }
    clean({ editingElement }) {
        // a notice saved before the captcha module carries reCAPTCHA's class
        editingElement
            .querySelector(".o_captcha_legal_terms, .o_recaptcha_legal_terms")
            .remove();
    }
}

registry
    .category("website-plugins")
    .add(CaptchaSubscribeOptionPlugin.id, CaptchaSubscribeOptionPlugin);
