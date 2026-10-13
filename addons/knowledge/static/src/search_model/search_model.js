/** @odoo-module native */
import { SearchModel } from "@web/search/search_model";

export const KnowledgeSearchModelMixin = (T) =>
    class extends T {
        setup(services, args) {
            this.saveEmbeddedViewFavoriteFilter = args.saveEmbeddedViewFavoriteFilter;
            this.deleteEmbeddedViewFavoriteFilter =
                args.deleteEmbeddedViewFavoriteFilter;
            super.setup(services, args);
        }

        /** @override */
        async load(config) {
            await super.load(config);
            if (config.state && !this.isStateCompleteForEmbeddedView) {
                const activateFavorite =
                    "activateFavorite" in config ? config.activateFavorite : true;
                if (activateFavorite) {
                    const defaultFavoriteId = this._createGroupOfFavorites(
                        this.irFilters || [],
                    );
                    if (defaultFavoriteId) {
                        this._activateDefaultSearchItems(defaultFavoriteId);
                    }
                }
            }
        }

        /** @override */
        async _createIrFilters(irFilter) {
            this.saveEmbeddedViewFavoriteFilter(irFilter);
            return null;
        }

        /** @override */
        _reconciliateFavorites() {}

        deleteFavorite(favoriteId) {
            const searchItem = this.searchItems[favoriteId];
            if (searchItem.type !== "favorite") {
                return;
            }
            this._deleteIrFilters(searchItem);
            const index = this.query.findIndex(
                (queryElem) => queryElem.searchItemId === favoriteId,
            );
            delete this.searchItems[favoriteId];
            if (index >= 0) {
                this.query.splice(index, 1);
            }
            this._notify();
        }

        _deleteIrFilters(searchItem) {
            this.deleteEmbeddedViewFavoriteFilter(searchItem);
        }

        /**
         * @override
         * @returns {Object}
         */
        exportState() {
            const state = super.exportState();
            state.isStateCompleteForEmbeddedView = true;
            return state;
        }

        /**
         * @override
         */
        _importState(state) {
            super._importState(state);
            this.isStateCompleteForEmbeddedView = state.isStateCompleteForEmbeddedView;
        }
    };

export class KnowledgeSearchModel extends KnowledgeSearchModelMixin(SearchModel) {}
