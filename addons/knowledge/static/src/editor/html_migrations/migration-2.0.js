/** @odoo-module native */
const SELECTOR = `[data-embedded="view"],[data-embedded="viewLink"]`;

/** @param {HTMLElement} container */
export function migrate(container) {
    for (const host of container.querySelectorAll(SELECTOR)) {
        migrateEmbeddedViewIrFilters(host);
    }
}

function migrateEmbeddedViewIrFilters(host) {
    if (!host.dataset.embeddedProps) {
        return;
    }
    const embeddedProps = JSON.parse(host.dataset.embeddedProps);
    if (embeddedProps.viewProps?.context?.knowledge_search_model_state) {
        migrateSearchModelState(embeddedProps);
    }
    if (embeddedProps.viewProps?.favoriteFilters) {
        migrateFavoriteFilters(embeddedProps);
    }
    host.dataset.embeddedProps = JSON.stringify(embeddedProps);
}

function migrateSearchModelState(embeddedProps) {
    const state = JSON.parse(
        embeddedProps.viewProps.context.knowledge_search_model_state,
    );
    if (!state.searchItems) {
        return;
    }
    for (const searchItem of Object.values(state.searchItems)) {
        if (searchItem.type !== "favorite") {
            continue;
        }
        delete searchItem.userId;
        searchItem.userIds = [];
    }
    embeddedProps.viewProps.context.knowledge_search_model_state =
        JSON.stringify(state);
}

function migrateFavoriteFilters(embeddedProps) {
    const favoriteFilters = embeddedProps.viewProps.favoriteFilters;
    for (const favorite of Object.values(favoriteFilters)) {
        delete favorite.user_id;
        favorite.user_ids = [];
    }
}
