/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class QuizReveal extends Interaction {
    static selector = ".o_we_track_quiz_button a[href='#we_track_quiz_container']";
    dynamicContent = {
        _root: { "t-on-click": this.onClick },
    };

    onClick() {
        document.getElementById("we_track_quiz_container")?.classList.remove("d-none");
    }
}

registry
    .category("public.interactions")
    .add("website_event_track_quiz.quiz_reveal", QuizReveal);
