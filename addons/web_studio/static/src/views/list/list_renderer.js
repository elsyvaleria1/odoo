/** @odoo-module native */
import "@web/webclient/promote_studio/promote_studio_list_renderer";

import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list";

export const patchListRendererStudio = () => ({
    setup() {
        super.setup(...arguments);
        this.studioService = useService("studio");
    },
    /** @override */
    onSelectedAddCustomField() {
        this.studioService.open();
    },

    isStudioEditable() {
        return !this.studioService?.mode && super.isStudioEditable();
    },
});

export const unpatchListRendererStudio = patch(
    ListRenderer.prototype,
    patchListRendererStudio(),
);
