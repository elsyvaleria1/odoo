/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class SurveyRanking extends Interaction {
    static selector = ".o_survey_ranking";

    dynamicContent = {
        "li[data-answer-id]": {
            "t-att-draggable": () => "true",
            "t-on-dragstart": this.onDragStart,
            "t-on-dragover.prevent": this.onDragOver,
            "t-on-dragend": this.onDragEnd,
            "t-on-keydown": this.onKeyDown,
            "t-att-tabindex": () => "0",
        },
    };

    setup() {
        this.dragged = null;
        this.listEl = this.el.querySelector(".o_survey_ranking_list");
    }

    start() {
        this.renumber();
    }

    renumber() {
        const items = this.listEl.querySelectorAll("li[data-answer-id]");
        items.forEach((itemEl, index) => {
            const position = index + 1;
            itemEl.querySelector(".o_survey_ranking_position").textContent = position;
            itemEl.querySelector("input[type=hidden]").value = position;
            itemEl.setAttribute("aria-posinset", position);
            itemEl.setAttribute("aria-setsize", items.length);
        });
    }

    onDragStart(ev) {
        this.dragged = ev.currentTarget;
        ev.dataTransfer.effectAllowed = "move";
        this.dragged.classList.add("opacity-50");
    }

    onDragOver(ev) {
        if (!this.dragged || ev.currentTarget === this.dragged) {
            return;
        }
        const target = ev.currentTarget;
        const { top, height } = target.getBoundingClientRect();
        const before = ev.clientY < top + height / 2;
        target.parentNode.insertBefore(
            this.dragged,
            before ? target : target.nextSibling,
        );
        this.renumber();
    }

    onDragEnd() {
        if (this.dragged) {
            this.dragged.classList.remove("opacity-50");
            this.dragged = null;
        }
        this.renumber();
    }

    onKeyDown(ev) {
        if (!ev.altKey || (ev.key !== "ArrowUp" && ev.key !== "ArrowDown")) {
            return;
        }
        ev.preventDefault();
        const itemEl = ev.currentTarget;
        const sibling =
            ev.key === "ArrowUp"
                ? itemEl.previousElementSibling
                : itemEl.nextElementSibling;
        if (!sibling) {
            return;
        }
        if (ev.key === "ArrowUp") {
            sibling.parentNode.insertBefore(itemEl, sibling);
        } else {
            sibling.parentNode.insertBefore(sibling, itemEl);
        }
        this.renumber();
        itemEl.focus();
    }
}

registry.category("public.interactions").add("survey.survey_ranking", SurveyRanking);
