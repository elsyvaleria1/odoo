// @ts-check
/** @odoo-module native */

import { Component, ErrorBoundary, onError, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useSortable } from "@web/core/utils/dnd";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

import { orderAfterDrag } from "../home_menu_layout.js";
import { HomeTilesModel } from "./home_tiles_model.js";

const log = makeLogger("web.home_tiles");

/**
 * @typedef {import("./home_tiles_model.js").TileEntry} TileEntry
 * @typedef {{ data?: any, error?: "failed" | "unavailable", loading?: boolean }} TileResult
 */

export const homeTileRegistry = registry.category("home_tiles");
homeTileRegistry.addValidation(
    t.object({
        Component: t.function(),
        Settings: t.function().optional(),
        title: t.function().optional(),
    }),
);

class HomeTileBoundary extends ErrorBoundary {
    setup() {
        super.setup();
        onError((/** @type {unknown} */ error) => {
            console.warn("Home tile failed to render", error);
            throw error;
        });
    }
}

export class HomeTiles extends Component {
    static template = "web.HomeTiles";
    static components = { HomeTileBoundary };
    static props = {
        editing: t.boolean(),
        model: t.instanceOf(HomeTilesModel),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.model = this.props.model;
        this.state = proxy({
            /** @type {Record<string, TileResult>} */
            results: {},
            /** @type {Record<string, { name: string, sizes: string[] }> | null} */
            types: null,
            picking: false,
            /** @type {string | null} */
            configuring: null,
            announcement: "",
        });
        /** @type {Promise<void> | null} */
        this.typesLoad = null;
        /** @type {Map<string, number>} */
        this.loads = new Map();
        this.loadRequest = 0;
        this.rootRef = elementRef();
        useSortable({
            enable: () => this.props.editing && !this.saving,
            ref: this.rootRef,
            elements: ".o_home_data_tile",
            ignore: "a, button, input, select, textarea",
            cursor: "move",
            onDrop: (params) => this.onDrop(params),
        });
        useLayoutEffect(
            (tiles) => {
                if (tiles.length) {
                    this.loadTypes();
                    this.load(tiles);
                }
            },
            () => [this.model.state.tiles],
        );
    }

    get tiles() {
        return this.model.state.tiles;
    }

    get saving() {
        return this.model.state.saving;
    }

    /** @param {TileEntry[]} tiles */
    async load(tiles) {
        const requested = tiles.filter(
            (tile) =>
                !this.state.results[tile.id]?.data &&
                !this.state.results[tile.id]?.loading,
        );
        if (!requested.length) {
            return;
        }
        const request = ++this.loadRequest;
        for (const tile of requested) {
            this.loads.set(tile.id, request);
            this.state.results[tile.id] = { loading: true };
        }
        /** @type {(id: string, result: TileResult) => void} */
        const settle = (id, result) => {
            if (this.loads.get(id) !== request) {
                log.logic("stale_answer", () => ({ id, request }));
                return;
            }
            this.loads.delete(id);
            this.state.results[id] = result;
        };
        const end = log.perf("load");
        try {
            const results = await this.orm.silent.call("home.tile", "get_tiles", [
                requested.map(({ id, type, settings }) => ({ id, type, settings })),
            ]);
            end({ tiles: requested.length });
            for (const { id } of requested) {
                settle(id, results[id] ?? { error: "failed" });
            }
        } catch (error) {
            end({ tiles: requested.length, error: String(error) });
            for (const { id } of requested) {
                settle(id, { error: "failed" });
            }
        }
    }

    /** @param {string} id */
    forget(id) {
        this.loads.delete(id);
        delete this.state.results[id];
    }

    /** @param {TileEntry} tile */
    isLoading(tile) {
        const result = this.state.results[tile.id];
        return !result || Boolean(result.loading);
    }

    /** @param {TileEntry} tile */
    dataOf(tile) {
        return this.state.results[tile.id]?.data;
    }

    /** @param {TileEntry} tile */
    componentOf(tile) {
        return homeTileRegistry.get(tile.type, null)?.Component ?? null;
    }

    /** @param {TileEntry} tile */
    settingsOf(tile) {
        return homeTileRegistry.get(tile.type, null)?.Settings ?? null;
    }

    /** @param {TileEntry} tile */
    titleOf(tile) {
        const data = this.dataOf(tile);
        const own = data && homeTileRegistry.get(tile.type, null)?.title?.(data);
        return own || this.state.types?.[tile.type]?.name || "";
    }

    /** @param {TileEntry} tile */
    canResize(tile) {
        return (this.state.types?.[tile.type]?.sizes.length ?? 0) > 1;
    }

    get addableTypes() {
        return Object.entries(this.state.types || {})
            .filter(([type]) => homeTileRegistry.contains(type))
            .map(([type, spec]) => ({ type, name: spec.name }));
    }

    loadTypes() {
        log.logic("load_types", () => ({ cached: Boolean(this.typesLoad) }));
        this.typesLoad ??= this.orm.silent.call("home.tile", "get_tile_types", []).then(
            (types) => {
                this.state.types = types;
            },
            (error) => {
                this.typesLoad = null;
                log.logic("load_types_failed", () => ({ error: String(error) }));
            },
        );
        return this.typesLoad;
    }

    async togglePicker() {
        await this.loadTypes();
        this.state.picking = !this.state.picking;
    }

    /** @param {string} type */
    async add(type) {
        this.state.picking = false;
        await this.model.change([{ operation: "add", type }]);
        const added = this.tiles.at(-1);
        if (added?.type !== type) {
            return;
        }
        this.state.announcement = _t("%s added", this.state.types?.[type]?.name ?? "");
        if (this.settingsOf(added)) {
            this.state.configuring = added.id;
        }
    }

    /**
     * @param {TileEntry} tile
     * @param {number} delta
     */
    moveTitle(tile, delta) {
        const title = this.titleOf(tile);
        return delta < 0 ? _t("Move %s earlier", title) : _t("Move %s later", title);
    }

    /**
     * @param {TileEntry} tile
     * @param {number} index
     */
    async moveTo(tile, index) {
        await this.model.change([{ operation: "move", id: tile.id, index }]);
        this.state.announcement = _t("%(tile)s moved to position %(position)s", {
            tile: this.titleOf(tile),
            position: index + 1,
        });
    }

    /**
     * @param {TileEntry} tile
     * @param {number} delta
     */
    move(tile, delta) {
        const index = this.tiles.indexOf(tile) + delta;
        if (index < 0 || index >= this.tiles.length) {
            return;
        }
        return this.moveTo(tile, index);
    }

    /** @param {import("@web/core/utils/dnd/sortable").DropParams} params */
    onDrop({ element, previous }) {
        const movedId = /** @type {HTMLElement} */ (element).dataset.tileId;
        const afterId = /** @type {HTMLElement | undefined} */ (previous)?.dataset
            .tileId;
        const ids = this.tiles.map((tile) => tile.id);
        const order = movedId && orderAfterDrag(ids, movedId, afterId);
        const tile = this.tiles.find((candidate) => candidate.id === movedId);
        if (!order || !tile || order.indexOf(movedId) === ids.indexOf(movedId)) {
            return;
        }
        return this.moveTo(tile, order.indexOf(movedId));
    }

    /** @param {TileEntry} tile */
    toggleSettings(tile) {
        this.state.configuring = this.state.configuring === tile.id ? null : tile.id;
    }

    /**
     * @param {TileEntry} tile
     * @param {Record<string, any>} settings
     */
    async configure(tile, settings) {
        this.state.configuring = null;
        const previous = this.state.results[tile.id];
        this.forget(tile.id);
        try {
            await this.model.change([
                { operation: "configure", id: tile.id, settings },
            ]);
        } catch (error) {
            if (previous && !previous.loading) {
                this.state.results[tile.id] = previous;
            } else {
                this.load([tile]);
            }
            throw error;
        }
    }

    /** @param {TileEntry} tile */
    async remove(tile) {
        const title = this.titleOf(tile);
        await this.model.change([{ operation: "remove", id: tile.id }]);
        this.forget(tile.id);
        this.state.announcement = _t("%s removed", title);
    }

    /** @param {TileEntry} tile */
    async resize(tile) {
        const sizes = this.state.types?.[tile.type]?.sizes ?? [];
        const next = sizes[(sizes.indexOf(tile.size) + 1) % sizes.length];
        await this.model.change([{ operation: "resize", id: tile.id, size: next }]);
        this.state.announcement =
            next === "2x1"
                ? _t("%s is now wide", this.titleOf(tile))
                : _t("%s is now narrow", this.titleOf(tile));
    }

    /** @param {TileEntry} tile */
    errorOf(tile) {
        const { error } = this.state.results[tile.id] || {};
        if (error === "unavailable") {
            return _t("This tile is no longer available to you.");
        }
        return error ? _t("This tile could not be loaded.") : "";
    }
}
