// @ts-check
/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

import { ImStatus } from "./im_status.js";
import { Thread } from "./thread_model.js";
/**
 * @typedef {Object} Props
 * @property {import("models").Thread} thread
 * @property {string} size
 * @property {string} className
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class ThreadIcon extends Component {
    static template = "mail.ThreadIcon";
    static components = { ImStatus };
    static props = {
        thread: t.instanceOf(Thread),
        size: t
            .customValidator(t.any(), (size) =>
                ["small", "medium", "large"].includes(size),
            )
            .optional("medium"),
        className: t.string().optional(""),
        title: t.boolean().optional(true),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.store = useService("mail.store");
    }

    get correspondent() {
        return this.props.thread.correspondent;
    }

    get defaultChatIcon() {
        return {
            class: "fa-solid fa-question-circle opacity-75",
            title: _t("No IM status available"),
        };
    }
}
