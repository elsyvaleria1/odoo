/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class PortalSearchPanel extends Interaction {
    static selector = ".o_portal_search_panel";
    dynamicContent = {
        ".dropdown-item": {
            "t-on-click.prevent.withTarget": this.onDropdownItemClick,
        },
        _root: {
            "t-on-submit.prevent": this.search,
        },
    };

    setup() {
        this.adaptSearchLabel(this.el.querySelector(".dropdown-item.active"));
    }

    adaptSearchLabel(elem) {
        if (!elem) {
            return;
        }
        const labelEl = elem.cloneNode(true);
        labelEl.querySelector("span.nolabel")?.remove();
        this.el
            .querySelector("input[name=search]")
            ?.setAttribute("placeholder", labelEl.textContent.trim());
    }

    search() {
        const url = new URL(browser.location.href);
        url.searchParams.set(
            "search_in",
            this.el
                .querySelector(".dropdown-item.active")
                ?.getAttribute("href")
                ?.replace("#", "") || "",
        );
        url.searchParams.set(
            "search",
            this.el.querySelector("input[name=search]")?.value || "",
        );
        url.pathname = url.pathname.replace(/\/page\/\d+\/?$/, "");
        const navigate = new CustomEvent("o-navigate", {
            bubbles: true,
            cancelable: true,
            detail: { url: url.toString() },
        });
        if (this.el.dispatchEvent(navigate)) {
            browser.location.assign(url.toString());
        }
    }

    onDropdownItemClick(ev, currentTargetEl) {
        currentTargetEl
            .closest(".dropdown-menu")
            .querySelector(".dropdown-item.active")
            ?.classList.remove("active");
        currentTargetEl.classList.add("active");

        this.adaptSearchLabel(currentTargetEl);
    }
}

registry
    .category("public.interactions")
    .add("portal.portal_search_panel", PortalSearchPanel);
