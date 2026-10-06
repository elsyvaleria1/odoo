// @ts-check
/** @odoo-module native */
import { useMailContext } from "@mail/utils/common/mail_context";
import { Component, t, useProps } from "@odoo/owl";

export class ImStatus extends Component {
    static props = {
        persona: t.any().optional(),
        className: t.any().optional(""),
        style: t.any().optional(""),
        member: t.any().optional(),
        slots: t.any().optional(),
        size: t.any().optional("lg"),
    };
    static template = "mail.ImStatus";
    static components = {};
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.mailContext = useMailContext();
    }

    get persona() {
        return this.props.persona ?? this.props.member?.persona;
    }
}
