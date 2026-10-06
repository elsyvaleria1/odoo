/** @odoo-module native */
import { loadBundle } from "@web/core/assets";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class ProfileEditor extends Interaction {
    static selector = ".o_wprofile_editor";
    dynamicContent = {
        _root: {
            "t-on-click.prevent": this.openDialog,
        },
    };

    async openDialog() {
        await this.waitFor(loadBundle("website_profile.assets_profile_dialog"));
        const ProfileDialog = registry
            .category("lazy_components")
            .get("website_profile.ProfileDialog");
        this.services.dialog.add(ProfileDialog, {
            confirm: () => {
                browser.location.reload();
            },
            focusWebsiteDescription:
                this.el.dataset.focusWebsiteDescription &&
                this.el.dataset.focusWebsiteDescription === "true",
            userId: parseInt(this.el.dataset.userId),
        });
    }
}

registry
    .category("public.interactions")
    .add("website_profile.profile_editor", ProfileEditor);
