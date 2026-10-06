/** @odoo-module native */
import { Composer } from "@mail/core/common/composer";
import { Thread } from "@mail/core/common/thread";
import { provideChildMailContext } from "@mail/utils/common/mail_context";
import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { useSpreadsheetEnv } from "@spreadsheet/hooks";
import { useService } from "@web/core/utils/hooks";

import { SpreadsheetCommentComposer } from "./spreadsheet_comment_composer.js";

export class CellThread extends Component {
    static template = "spreadsheet_edition.CellThread";
    static components = { Thread, Composer, SpreadsheetCommentComposer };

    static props = { threadId: t.number(), edit: t.boolean() };
    static threadModel = "spreadsheet.cell.thread";
    props = useProps(this.constructor.props);
    env = useSpreadsheetEnv();

    setup() {
        provideChildMailContext({
            inChatWindow: true,
            chatter: {},
        });
        /** @type {import("models").Store} */
        this.mailStore = useService("mail.store");
        this.state = proxy({
            /** @type {import("models").Thread} */
            thread: undefined,
        });
        onWillStart(() => this.loadThread(this.props.threadId));

        onWillUpdateProps(async (nextProps) => {
            if (this.props.threadId !== nextProps.threadId) {
                await this.loadThread(nextProps.threadId);
            }
        });
    }

    async loadThread(threadId) {
        this.state.thread = this.mailStore.Thread.insert({
            model: CellThread.threadModel,
            id: threadId,
        });
        await this.state.thread.fetchNewMessages();
    }
}
