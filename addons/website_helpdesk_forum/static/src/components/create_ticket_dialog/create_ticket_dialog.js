/** @odoo-module native */
import { Component, markup, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class CreateTicketDialog extends Component {
    static template = "website_helpdesk_forum.CreateTicketDialog";
    static components = { Dialog };
    static props = {
        forumId: t.number(),
        postId: t.number(),
        close: t.function().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({});
        this.inputText = elementRef();
        this.notification = useService("notification");
        this.orm = useService("orm");

        onWillStart(async () => {
            const forumPostData = await rpc(window.location.href + "/get-forum-data");
            this.state.data = {
                ...forumPostData,
                team_id: forumPostData.teams?.[0]?.[0],
            };
        });
    }

    _createTicket() {
        return this.orm.call("forum.forum", "create_ticket", [
            this.props.forumId,
            this.props.postId,
            this.state.data,
        ]);
    }

    _checkInputIsValid() {
        const isValid = this.inputText.el.value.trim().length;
        this.inputText.el.classList.toggle("is-invalid", !isValid);
        return isValid;
    }

    async onCreateTicket() {
        if (!this._checkInputIsValid()) {
            return;
        }
        const response = await this._createTicket();
        const message = _t(
            "Helpdesk ticket %(ticket)s has been successfully created for this forum post.",
            { ticket: markup`<b>#${response.ticket}</b>` },
        );
        this.notification.add(message, { type: "success" });
        this.props.close();
    }

    async onCreateAndViewTicket() {
        if (!this._checkInputIsValid()) {
            return;
        }
        const response = await this._createTicket();
        window.open(response.url, "_blank");
        this.props.close();
    }
}
