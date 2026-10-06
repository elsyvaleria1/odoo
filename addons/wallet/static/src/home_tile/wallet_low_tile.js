// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { HomeTileRecordLink } from "@web/webclient/home_menu/home_tiles/home_tile_record_link";
import { homeTileRegistry } from "@web/webclient/home_menu/home_tiles/home_tiles";

/**
 * @typedef {{ id: number, name: string, account: string, balance: string, threshold: string }} LowCard
 */

export class WalletLowTile extends Component {
    static template = "wallet.WalletLowTile";
    static components = { HomeTileRecordLink };
    static props = {
        data: t.object({ count: t.number(), cards: t.array() }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    /** @returns {LowCard[]} */
    get cards() {
        return this.props.data.cards.slice(0, this.props.size === "2x1" ? 6 : 3);
    }

    openAll() {
        return this.action.doAction("wallet.action_wallet_card", {
            additionalContext: { search_default_low_balance: 1 },
        });
    }
}

homeTileRegistry.add("wallet_low", { Component: WalletLowTile });
