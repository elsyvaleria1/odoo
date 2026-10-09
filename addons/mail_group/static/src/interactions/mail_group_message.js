/** @odoo-module native */
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class MailGroupMessage extends Interaction {
    static selector = ".o_mg_message";

    start() {
        const quoted = [
            ...this.el.querySelectorAll(".card-body [data-o-mail-quote]"),
        ].filter((node) => node.closest(".o_mg_message") === this.el);
        if (quoted.length > 0) {
            const readMore = document.createElement("button");
            readMore.classList.add("btn", "btn-light", "btn-sm", "ms-1");
            readMore.innerText = ". . .";
            this.insert(readMore, quoted[0], "beforebegin");
            this.addListener(readMore, "click", () =>
                quoted.forEach((node) => node.classList.toggle("visible")),
            );
        }
    }
}

export class MailGroupToggle extends Interaction {
    static selector = ".o_mg_link_parent";
    dynamicContent = {
        ":scope > p > .o_mg_link_hide": {
            "t-on-click.prevent.stop": () => (this.expanded = true),
            "t-att-class": () => ({ "d-none": this.expanded }),
        },
        ":scope > p > .o_mg_link_show": {
            "t-on-click.prevent.stop": () => (this.expanded = false),
            "t-att-class": () => ({ "d-none": !this.expanded }),
        },
        ":scope > .o_mg_link_content": {
            "t-att-class": () => ({ "d-none": !this.expanded }),
        },
    };

    setup() {
        this.expanded = false;
    }
}

export class MailGroupReadMore extends Interaction {
    static selector = ".o_mg_read_more";
    dynamicContent = {
        _root: { "t-on-click": this.locked(this.loadReplies) },
    };

    async loadReplies() {
        const html = await this.waitFor(
            rpc(this.el.dataset.href, {
                last_displayed_id: this.el.dataset.lastDisplayedId,
            }),
        );
        const row = this.el.closest("p");
        if (html) {
            const page = new DOMParser().parseFromString(html, "text/html").body
                .firstElementChild;
            const list = row.parentElement.querySelector(":scope > ul");
            for (const reply of page.querySelectorAll(":scope > ul > li")) {
                this.insert(reply, list, "beforeend", false);
            }
            const nextRow = page.querySelector(":scope > p:has(> .o_mg_read_more)");
            if (nextRow) {
                this.insert(nextRow, row, "afterend", false);
            }
        }
        this.services["public.interactions"].stopInteractions(row);
        row.remove();
    }
}

registry
    .category("public.interactions")
    .add("mail_group.mail_group_message", MailGroupMessage)
    .add("mail_group.mail_group_toggle", MailGroupToggle)
    .add("mail_group.mail_group_read_more", MailGroupReadMore);
