/** @odoo-module native */
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { KanbanHeader, KanbanRenderer } from "@web/views/kanban";

import { ImagesCarouselDialog } from "./images_carousel_dialog.js";
import { StreamPostKanbanRecord } from "./stream_post_kanban_record.js";

class StreamPostKanbanHeader extends KanbanHeader {
    static template = "social.KanbanHeader";

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}

export class StreamPostKanbanRenderer extends KanbanRenderer {
    static components = {
        ...KanbanRenderer.components,
        KanbanRecord: StreamPostKanbanRecord,
        KanbanHeader: StreamPostKanbanHeader,
    };
    setup() {
        super.setup();

        this.dialog = useService("dialog");
        const rootRef = this.rootRef;
        useLayoutEffect(
            (images) => {
                const onClickMoreImages = this.onClickMoreImages.bind(this);
                images.forEach((image) =>
                    image.addEventListener("click", onClickMoreImages),
                );
                return () => {
                    images.forEach((image) =>
                        image.removeEventListener("click", onClickMoreImages),
                    );
                };
            },
            () => [rootRef.el.querySelectorAll(".o_social_stream_post_image_more")],
        );
    }

    /**
     * Shows a bootstrap carousel starting at the clicked image's index
     *
     * @param {PointerEvent} ev - event of the clicked image
     */
    onClickMoreImages(ev) {
        ev.stopPropagation();
        this.dialog.add(ImagesCarouselDialog, {
            title: _t("Post Images"),
            activeIndex: parseInt(ev.currentTarget.dataset.index),
            images: ev.currentTarget.dataset.imageUrls.split(","),
        });
    }

    /**
     * Always display the no-content helper, even if there are groups.
     */
    get showNoContentHelper() {
        const { model } = this.props.list;
        return !model.hasData();
    }
}
