// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { homeTileRegistry } from "@web/webclient/home_menu/home_tiles/home_tiles";

/**
 * @typedef {{ id: number, name: string, type: string, to_reconcile: number, to_validate: number, late: number }} JournalRow
 */

const BANK_TYPES = new Set(["bank", "cash", "credit"]);

export class JournalsTile extends Component {
    static template = "account.JournalsTile";
    static props = {
        data: t.object({
            to_reconcile: t.number(),
            to_validate: t.number(),
            late: t.number(),
            journals: t.array(),
        }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
    }

    /** @returns {JournalRow[]} */
    get journals() {
        return this.props.data.journals.slice(0, this.props.size === "2x1" ? 6 : 3);
    }

    openDashboard() {
        return this.action.doAction("account.open_account_journal_dashboard_kanban");
    }

    /** @param {JournalRow} journal */
    contextOf(journal) {
        if (BANK_TYPES.has(journal.type)) {
            return {};
        }
        if (journal.late) {
            return {
                search_default_late: "1",
                search_default_posted: "1",
                journal_type: journal.type,
            };
        }
        return { search_default_draft: "1" };
    }

    /** @param {JournalRow} journal */
    async open(journal) {
        const action = await this.orm.call(
            "account.journal",
            "open_action",
            [[journal.id]],
            {
                context: this.contextOf(journal),
            },
        );
        return this.action.doAction(action);
    }
}

homeTileRegistry.add("journals", { Component: JournalsTile });
