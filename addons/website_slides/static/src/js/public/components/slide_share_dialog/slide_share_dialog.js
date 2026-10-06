/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { CopyButton } from "@web/components/copy_button";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { Dialog } from "@web/ui/dialog";

import { EmailSharingInput } from "./email_sharing_input.js";

export class SlideShareDialog extends Component {
    static template = "website_slides.SlideShareDialog";
    static components = { Dialog, CopyButton, EmailSharingInput };
    static props = {
        category: t.string().optional(),
        close: t.function(),
        documentMaxPage: t.number().optional(),
        emailSharing: t.boolean().optional(),
        embedCode: t.string().optional(),
        id: t.number(),
        isChannel: t.boolean().optional(),
        isFullscreen: t.boolean().optional(),
        name: t.string(),
        url: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.codeInput = elementRef();
        this.copyUrlText = _t("Copy Link");
        this.copyEmbedCodeText = _t("Copy Embed Code");
        this.successText = _t("Copied");
    }

    onSocialShareClick(url) {
        browser.open(url, "Share Dialog", "width=626,height=436");
    }

    onPageChange(event) {
        const page = event.currentTarget.value;
        const newEmbedCodeValue = this.codeInput.el.value.replace(
            /(page=).*?([^\d]+)/,
            "$1" + page + "$2",
        );
        this.codeInput.el.value = newEmbedCodeValue;
    }
}
