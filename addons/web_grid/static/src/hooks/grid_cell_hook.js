/** @odoo-module native */
import { useLayoutEffect } from "@web/core/utils/layout_effect";

/**
 * @param {HTMLElement | null | undefined} cellEl
 * @param {boolean} hidden
 */
export function setCellReadonlyHidden(cellEl, hidden) {
    cellEl?.querySelector(".o_grid_cell_readonly")?.classList.toggle("d-none", hidden);
}

export function useGridCell(component) {
    useLayoutEffect(
        /** @param {HTMLElement | null} cellEl */
        (cellEl) => {
            if (!cellEl) {
                component.state.cell = null;
                return;
            }
            component.state.cell = component.props.getCell(
                cellEl.dataset.row,
                cellEl.dataset.column,
            );
            Object.assign(component.rootRef.el.style, {
                "grid-row": cellEl.style["grid-row"],
                "grid-column": cellEl.style["grid-column"],
                "z-index": 1,
            });
            component.rootRef.el.dataset.gridRow = cellEl.dataset.gridRow;
            component.rootRef.el.dataset.gridColumn = cellEl.dataset.gridColumn;
            setCellReadonlyHidden(cellEl, true);
            component.rootRef.el.classList.toggle(
                "o_field_cursor_disabled",
                !component.state.cell.row.isSection && !component.isEditable(),
            );
            component.rootRef.el.classList.toggle(
                "fw-bold",
                Boolean(component.state.cell.row.isSection),
            );
        },
        () => [component.props.reactive.cell],
    );
}
