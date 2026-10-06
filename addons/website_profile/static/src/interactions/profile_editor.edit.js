/** @odoo-module native */
import { registry } from "@web/core/registry";
import { ProfileEditor } from "@website_profile/interactions/profile_editor";

const ProfileEditorEdit = (I) =>
    class extends I {
        setup() {}
        async willStart() {}
    };

registry
    .category("public.interactions.edit")
    .add("website_profile.website_profile_editor", {
        Interaction: ProfileEditor,
        mixin: ProfileEditorEdit,
    });
