/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import { SlideUploadDialog } from "@website_slides/js/public/components/slide_upload_dialog/slide_upload_dialog";
import { parseSlideBoolean } from "@website_slides/js/public/slides_course_utils";

export class SlideUpload extends Interaction {
    static selector = ".o_wslides_js_slide_upload";
    dynamicContent = {
        _root: {
            "t-on-click.prevent": () => this.openDialog(),
        },
    };

    start() {
        const openModal = this.el.dataset.openModal;
        if (openModal !== undefined) {
            delete this.el.dataset.openModal;
            this.openDialog(openModal);
        }
    }

    /**
     * @param {string} [openModal]
     */
    openDialog(openModal) {
        const data = this.el.dataset;
        this.services.dialog.add(SlideUploadDialog, {
            categoryId: data.categoryId ? parseInt(data.categoryId) : undefined,
            channelId: parseInt(data.channelId),
            canPublish: parseSlideBoolean(data.canPublish),
            canUpload: parseSlideBoolean(data.canUpload),
            openModal,
        });
    }
}

registry
    .category("public.interactions")
    .add("website_slides.slide_upload", SlideUpload);
