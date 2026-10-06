/** @odoo-module native */
import { Thread } from "@mail/core/common/thread";
import { provideChildMailContext } from "@mail/utils/common/mail_context";
import { stores } from "@odoo/o-spreadsheet";
import { Component, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { useSpreadsheetEnv } from "@spreadsheet/hooks";
import { useService } from "@web/core/utils/hooks";

import { CommentsStore } from "../comments_store.js";
import { CellThread } from "./cell_thread.js";
import { SpreadsheetCommentComposer } from "./spreadsheet_comment_composer.js";

const { useStore } = stores;

export class CellThreadPopover extends Component {
    static template = "spreadsheet_edition.CellThreadPopover";
    static components = { Thread, CellThread, SpreadsheetCommentComposer };

    static props = {
        threadId: t.number().optional(),
        onClosed: t.function().optional(),
        isInteractive: t.boolean(),
        position: t.object(),
        focus: t.any().optional(false),
    };

    static threadModel = "spreadsheet.cell.thread";
    props = useProps(this.constructor.props);
    env = useSpreadsheetEnv();

    setup() {
        provideChildMailContext({
            inChatWindow: true,
        });

        /** @type {import("models").Store} */
        this.mailStore = useService("mail.store");
        this.state = proxy({
            /** @type {import("models").Thread} */
            thread: undefined,
            isValid: true,
        });
        this.loadThread(this.props.threadId);

        this.commentsStore = useStore(CommentsStore);

        onWillUpdateProps((nextProps) => {
            this.loadThread(nextProps.threadId);
        });
    }

    onFocused() {
        if (this.props.threadId && !this.props.isInteractive) {
            this.commentsStore.openCommentThread(this.props.threadId);
        }
    }

    showAllComments() {
        this.env.openSidePanel("Comments");
    }

    loadThread(threadId) {
        this.state.thread = this.mailStore.Thread.insert({
            model: CellThreadPopover.threadModel,
            id: threadId,
        });
    }

    async insertNewThread(value, postData) {
        if (!value) {
            return;
        }
        const sheetId = this.env.model.getters.getActiveSheetId();
        const threadId = await this.env.insertThreadInSheet({
            sheetId,
            ...this.props.position,
        });
        this.loadThread(threadId);
        await this.state.thread.post(value, postData);
        this.commentsStore.openCommentThread(this.props.threadId);
    }
}
