/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class TicketDetails extends Interaction {
    static selector = ".o_wevent_js_ticket_details";
    dynamicContent = {
        "button[data-increment-type='minus']": {
            "t-on-click": (ev) => this.onClick(ev, -1),
        },
        "button[data-increment-type='plus']": {
            "t-on-click": (ev) => this.onClick(ev, 1),
        },
        ".o_wevent_input_nb_tickets": {
            "t-on-input": this.onInput,
        },
        ".a-submit": {
            "t-att-disabled": () =>
                this.moreTicketsOrderedThanExpected || this.noTicketsOrdered
                    ? "disabled"
                    : false,
        },
    };

    get noTicketsOrdered() {
        return Boolean(
            !Array.from(this.el.querySelectorAll(".o_wevent_input_nb_tickets")).find(
                (input) =>
                    Number.isNaN(parseInt(input.value))
                        ? false
                        : parseInt(input.value) > 0,
            ),
        );
    }

    get moreTicketsOrderedThanExpected() {
        return Boolean(
            Array.from(this.el.querySelectorAll(".o_wevent_input_nb_tickets")).find(
                (input) =>
                    Number.isNaN(parseInt(input.value))
                        ? true
                        : input.max < parseInt(input.value),
            ),
        );
    }

    /**
     * @param {InputEvent} ev
     */
    async onInput(ev) {
        const inputComponent = ev.target;
        const maximumBound = inputComponent.max;
        inputComponent.value = Math.min(
            inputComponent.value.replace(/[^0-9]/g, ""),
            maximumBound,
        );

        const spinner_buttons = this.el.querySelectorAll(
            `button[data-input-name=${inputComponent.name}]`,
        );
        spinner_buttons[0].disabled = parseInt(inputComponent.value) <= 0;
        spinner_buttons[1].disabled = parseInt(inputComponent.value) >= maximumBound;

        this.el.querySelector(`p[name=${inputComponent.name}]`).hidden =
            parseInt(inputComponent.value) < maximumBound;
    }

    /**
     * @param {MouseEvent} ev
     */
    onClick(ev, incrementValue) {
        const inputComponent = this.el.querySelector(
            `input[name=${ev.currentTarget.dataset.inputName}]`,
        );
        const maximumBound = inputComponent.max;
        const inputValue = parseInt(inputComponent.value);
        if (0 <= inputValue && inputValue <= maximumBound) {
            inputComponent.value = Math.max(
                0,
                Math.min(inputValue + incrementValue, maximumBound),
            );
        } else {
            inputComponent.value = inputValue < 0 ? 0 : maximumBound;
        }

        inputComponent.dispatchEvent(new Event("input"));
    }
}

registry
    .category("public.interactions")
    .add("website_event.ticket_details", TicketDetails);
