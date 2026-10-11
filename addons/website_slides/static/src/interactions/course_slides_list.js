/** @odoo-module native */
import { registry } from "@web/core/registry";
import { CoursePage } from "@website_slides/interactions/course_page";
import { syncEmptySectionFlags } from "@website_slides/js/public/slides_course_utils";

export class CourseSlidesList extends CoursePage {
    static selector = ".o_wslides_slides_list";

    start() {
        this.channelId = this.el.dataset.channelId;
        this.updateHref();
        this.bindSortable();
    }

    bindSortable() {
        const sortableBaseParam = {
            clone: false,
            placeholderClasses: [
                "o_wslides_slides_list_slide_hilight",
                "position-relative",
                "mb-1",
            ],
            onDrop: this.reorderSlides.bind(this),
            applyChangeOnDrop: true,
        };

        const containerEl = this.el.querySelector(
            "ul.o_wslides_js_slides_list_container",
        );
        const categorySortable = this.services.sortable
            .create({
                ...sortableBaseParam,
                ref: { el: containerEl },
                elements: ".o_wslides_slide_list_category",
                handle: ".o_wslides_slide_list_category_header .o_wslides_slides_list_drag",
                sortableId: "category",
            })
            .enable();
        this.registerCleanup(() => categorySortable.cleanup());

        const slideSortable = this.services.sortable
            .create({
                ...sortableBaseParam,
                ref: { el: containerEl },
                elements:
                    ".o_wslides_slides_list_slide:not(.o_wslides_js_slides_list_empty):not(.o_not_editable)",
                handle: ".o_wslides_slides_list_drag",
                connectGroups: true,
                groups: ".o_wslides_js_slides_list_container ul",
                sortableId: "list",
            })
            .enable();
        this.registerCleanup(() => slideSortable.cleanup());
    }

    /**
     * @returns {number[]}
     */
    getSlides() {
        const slideIds = [];
        for (const el of this.el.querySelectorAll(".o_wslides_js_list_item")) {
            slideIds.push(parseInt(el.dataset.slideId));
        }
        return slideIds;
    }

    async reorderSlides() {
        await this.waitFor(
            this.services.orm.webResequence("slide.slide", this.getSlides()),
        );
        syncEmptySectionFlags(this.el);
    }

    updateHref() {
        for (const linkEl of this.el.querySelectorAll(
            ".o_wslides_js_slides_list_slide_link",
        )) {
            const href = linkEl.getAttribute("href");
            const operator = href.indexOf("?") !== -1 ? "&" : "?";
            linkEl.setAttribute("href", href + operator + "fullscreen=1");
        }
    }
}

registry
    .category("public.interactions")
    .add("website_slides.course_slides_list", CourseSlidesList);
