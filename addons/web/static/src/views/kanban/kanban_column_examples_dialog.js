// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { Notebook } from "@web/components/notebook/notebook";
import { elementRef } from "@web/core/utils/element_ref";
import { withDefaults } from "@web/core/utils/props";
import { Dialog } from "@web/ui/dialog/dialog";

/**
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
const random = (min, max) => Math.floor(Math.random() * (max - min) + min);

class KanbanExamplesNotebookTemplate extends Component {
    static template = "web.KanbanExamplesNotebookTemplate";
    static props = null;
    props = withDefaults(
        useProps(this.constructor.props),
        this.constructor.defaultProps,
    );
    static defaultProps = {
        columns: [],
        foldedColumns: [],
    };
    setup() {
        this.columns = [];
        const hasBullet = this.props.bullets && this.props.bullets.length;
        const allColumns = [...this.props.columns, ...this.props.foldedColumns];
        for (const title of allColumns) {
            /** @type {Record<string, any>[]} */
            const records = [];
            this.columns.push({ title, records });
            for (let i = 0; i < random(1, 5); i++) {
                /** @type {Record<string, any>} */
                const rec = { id: i };
                if (hasBullet && Math.random() > 0.3) {
                    const sampleId = Math.floor(
                        Math.random() * this.props.bullets.length,
                    );
                    rec.bullet = this.props.bullets[sampleId];
                }
                records.push(rec);
            }
        }
    }
}

export class KanbanColumnExamplesDialog extends Component {
    static template = "web.KanbanColumnExamplesDialog";
    static components = { Dialog, Notebook };
    static props = {
        examples: t.array(t.object()),
        applyExamples: t.function(),
        applyExamplesText: t.string().optional(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    /** @type {Record<string, any>[]} */
    pages;
    /** @type {string | null} */
    activePage;

    setup() {
        this.navList = elementRef();
        this.pages = [];
        this.activePage = null;
        this.props.examples.forEach((eg) => {
            this.pages.push({
                Component: KanbanExamplesNotebookTemplate,
                title: eg.name,
                props: eg,
                id: eg.name,
            });
        });
    }

    /** @param {string} page */
    onPageUpdate(page) {
        this.activePage = page;
    }

    applyExamples() {
        const index = this.props.examples.findIndex((e) => e.name === this.activePage);
        this.props.applyExamples(index);
        this.props.close();
    }
}
