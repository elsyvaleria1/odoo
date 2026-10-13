// @ts-check
/** @odoo-module native */

import { proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { user } from "@web/core/user";
import { Mutex } from "@web/core/utils/concurrency";
import { session } from "@web/session";

const log = makeLogger("web.home_tiles");

/**
 * @typedef {{ id: string, type: string, size: string, settings?: Record<string, any> }} TileEntry
 * @typedef {{ version: number, tiles: TileEntry[] }} HomeTilesLayout
 */

/**
 * @param {any} layout
 * @returns {TileEntry[]}
 */
function tilesOf(layout) {
    const tiles = layout?.tiles;
    return Array.isArray(tiles) ? tiles : [];
}

/**
 * @param {any} own
 * @returns {string | null}
 */
export function homeBackgroundOf(own) {
    return (own || session.home_tiles_default)?.background ?? null;
}

/** @param {string | null} tint */
export function applyCanvasTint(tint) {
    if (tint) {
        document.body.dataset.homeTint = tint;
    } else {
        delete document.body.dataset.homeTint;
    }
}

export class HomeTilesModel {
    /** @param {{ orm: any }} services */
    constructor({ orm }) {
        this.orm = orm;
        this.mutex = new Mutex();
        this.queued = 0;
        this.state = proxy({
            tiles: this.resolve(user.settings?.home_tiles),
            /** @type {string | null} */
            background: homeBackgroundOf(user.settings?.home_tiles),
            personal: Boolean(user.settings?.home_tiles),
            saving: false,
        });
    }

    /** @param {any} own */
    resolve(own) {
        return tilesOf(own || session.home_tiles_default);
    }

    /** @param {string | null} value */
    setBackground(value) {
        return this.change([{ operation: "background", value }]);
    }

    /** @param {object[]} changes */
    async change(changes) {
        this.queued++;
        this.state.saving = true;
        try {
            await this.mutex.exec(async () => {
                const settings = await this.orm.call(
                    "res.users.settings",
                    "update_home_tiles",
                    [[user.settings.id], changes],
                );
                user.updateUserSettings("home_tiles", settings.home_tiles);
                this.state.personal = Boolean(settings.home_tiles);
                this.state.tiles = this.resolve(settings.home_tiles);
                this.state.background = homeBackgroundOf(settings.home_tiles);
                log.logic("changed", () => ({
                    changes,
                    tiles: this.state.tiles.length,
                    personal: this.state.personal,
                }));
            });
        } finally {
            this.state.saving = --this.queued > 0;
        }
    }

    reset() {
        return this.change([{ operation: "reset" }]);
    }

    async setCompanyDefault() {
        await this.mutex.getUnlockedDef();
        const { tiles, background } = this.state;
        const layout = await this.orm.call("web.config", "set_home_tiles_default", [
            { version: 1, tiles, ...(background && { background }) },
        ]);
        session.home_tiles_default = layout;
        log.logic("company_default", () => ({ tiles: tilesOf(layout).length }));
    }
}
