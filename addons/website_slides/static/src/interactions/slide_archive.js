/** @odoo-module native */
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Interaction } from "@web/public/interaction";
import { ConfirmationDialog } from "@web/ui/dialog";
import { syncEmptySectionFlags } from "@website_slides/js/public/slides_course_utils";

export class SlideArchive extends Interaction {
    static selector = ".o_wslides_js_slide_archive";
    dynamicContent = {
        _root: {
            "t-on-click.prevent": this.openDialog,
        },
    };

    openDialog() {
        const slideId = this.el.dataset.slideId;
        this.services.dialog.add(ConfirmationDialog, {
            title: _t("Archive Content"),
            body: _t("Are you sure you want to archive this content?"),
            confirmLabel: _t("Archive"),
            confirm: async () => {
                const isArchived = await this.waitFor(
                    rpc("/slides/slide/archive", { slide_id: slideId }),
                );
                if (isArchived) {
                    this.el.closest(".o_wslides_slides_list_slide")?.remove();
                    syncEmptySectionFlags(document);
                }
            },
            cancel: () => {},
        });
    }
}

registry
    .category("public.interactions")
    .add("website_slides.slide_archive", SlideArchive);
