/** @odoo-module native */
import { Domain } from "@web/core/domain";
import { SearchModel } from "@web/search/search_model";

export const HighlightProjectTaskSearchModelMixin = (T) =>
    class HighlightProjectTaskSearchModel extends T {
        exportState() {
            return {
                ...super.exportState(),
                highlightIds: this.highlightIds,
            };
        }

        _importState(state) {
            this.highlightIds = state.highlightIds ?? null;
            super._importState(state);
        }

        _getDomain(params = {}) {
            const domain = super._getDomain(params);
            if (!this.highlightIds) {
                return domain;
            }
            const highlighted = Domain.and([domain, [["id", "in", this.highlightIds]]]);
            return params.raw ? highlighted : highlighted.toList();
        }

        async load(config) {
            await super.load(config);
            await this._syncHighlightIds();
        }

        _notify(options) {
            // a blocked notification is replayed through _notify once unblocked
            const fetching = this.blockNotification ? null : this._syncHighlightIds();
            return fetching
                ? fetching.then(() => super._notify(options))
                : super._notify(options);
        }

        /** @returns {Promise<void> | null} */
        _syncHighlightIds() {
            // the query may have changed since the context was last memoized
            this._reset();
            if (!this.context.highlight_conflicting_task) {
                this.highlightIds = null;
                this._highlightIdsFetch = null;
                return null;
            }
            if (this.highlightIds) {
                return null;
            }
            if (!this._highlightIdsFetch) {
                const fetch = this.orm
                    .search("project.task", [["planning_overlap", "!=", false]])
                    .then((ids) => {
                        if (this._highlightIdsFetch === fetch) {
                            this.highlightIds = ids;
                            this._highlightIdsFetch = null;
                        }
                    });
                this._highlightIdsFetch = fetch;
            }
            return this._highlightIdsFetch;
        }
    };

export class HighlightProjectTaskSearchModel extends HighlightProjectTaskSearchModelMixin(
    SearchModel,
) {}
