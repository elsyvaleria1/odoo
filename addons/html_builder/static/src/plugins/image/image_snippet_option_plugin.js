/** @odoo-module native */
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";

class ImageSnippetOptionPlugin extends Plugin {
    static id = "imageSnippetOption";
    static dependencies = ["media"];
    static shared = ["onSnippetDropped"];
    /** @type {import("plugins").BuilderResources} */
    resources = {
        on_snippet_dropped_handlers: this.onSnippetDropped.bind(this),
        so_content_addition_selector: [".s_image"],
    };

    async onSnippetDropped({ snippetEl, dragState }) {
        if (!snippetEl.matches(".s_image")) {
            return;
        }

        let isImageSelected = false;
        await new Promise((resolve) => {
            const onClose = this.dependencies.media.openMediaDialog({
                onlyImages: true,
                save: async (selectedImageEl) => {
                    isImageSelected = true;
                    snippetEl.replaceWith(selectedImageEl);
                    if (dragState.draggedEl.classList.contains("o_grid_item")) {
                        dragState.draggedEl.classList.add("o_grid_item_image");
                    }
                    dragState.replacedSnippetEl = selectedImageEl;
                },
            });
            onClose.then(() => {
                resolve();
            });
        });

        return !isImageSelected;
    }
}

registry
    .category("builder-plugins")
    .add(ImageSnippetOptionPlugin.id, ImageSnippetOptionPlugin);
