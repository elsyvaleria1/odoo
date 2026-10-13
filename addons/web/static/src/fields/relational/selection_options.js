// @ts-check
/** @odoo-module native */

/**
 * @template T
 * @param {T[]} options
 * @param {number[]} selectedIds
 * @param {(option: T) => number} getId
 * @param {(ids: number[]) => Promise<T[]>} loadMissing
 * @returns {Promise<T[]>}
 */
export async function completeSelectedOptions(
    options,
    selectedIds,
    getId,
    loadMissing,
) {
    const shownIds = new Set(options.map(getId));
    const missingIds = selectedIds.filter((id) => !shownIds.has(id));
    if (!missingIds.length) {
        return options;
    }
    return [...options, ...(await loadMissing(missingIds))];
}
