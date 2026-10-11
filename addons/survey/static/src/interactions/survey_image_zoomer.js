/** @odoo-module native */
import { fadeIn, fadeOut } from "@survey/utils";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class SurveyImageZoomer extends Interaction {
    static selector = ".o_survey_img_zoom_modal";
    dynamicContent = {
        _root: {
            "t-on-click.prevent": this.onZoomerClick,
        },
        ".o_survey_img_zoom_image": {
            "t-on-wheel": this.onImageScroll,
            "t-att-style": () => ({
                transform: `scale(${this.zoomImageScale}) !important`,
            }),
        },
        ".o_survey_img_zoom_in_btn": {
            "t-on-click.stop": () => this.addZoomSteps(1),
        },
        ".o_survey_img_zoom_out_btn": {
            "t-on-click.stop": () => this.addZoomSteps(-1),
        },
    };

    setup() {
        this.fadeInOutDelay = 200;
        this.zoomImageScale = 1;
    }

    async willStart() {
        await fadeOut(this.el, 0);
        fadeIn(this.el, this.fadeInOutDelay);
    }

    /**
     * Zoom in/out image on scrolling
     * @param {WheelEvent} ev
     */
    onImageScroll(ev) {
        ev.preventDefault();
        if (ev.wheelDelta > 0 || ev.detail < 0) {
            this.addZoomSteps(1);
        } else {
            this.addZoomSteps(-1);
        }
    }

    async onZoomerClick() {
        await this.waitFor(fadeOut(this.el, this.fadeInOutDelay));
        this.el.remove();
    }

    /**
     * Zoom in / out the image by changing the scale by the given number of steps.
     * @param {integer} zoomStepNumber - Number of zoom steps applied to the scale of
     * the image. It can be negative, in order to zoom out. Step is set to 0.1.
     */
    addZoomSteps(zoomStepNumber) {
        const image = this.el.querySelector(".o_survey_img_zoom_image");
        const body = this.el.querySelector(".o_survey_img_zoom_body");
        const imageWidth = image.clientWidth;
        const imageHeight = image.clientHeight;
        const bodyWidth = body.clientWidth;
        const bodyHeight = body.clientHeight;
        const newZoomImageScale = this.zoomImageScale + zoomStepNumber * 0.1;
        if (newZoomImageScale <= 0.2) {
            return;
        }
        if (
            zoomStepNumber > 0 &&
            (imageWidth * newZoomImageScale > bodyWidth ||
                imageHeight * newZoomImageScale > bodyHeight)
        ) {
            return;
        }
        this.zoomImageScale = newZoomImageScale;
    }
}

registry
    .category("public.interactions")
    .add("survey.SurveyImageZoomer", SurveyImageZoomer);
