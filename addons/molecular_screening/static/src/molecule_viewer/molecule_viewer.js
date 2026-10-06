import { onMounted, onPatched, onWillStart, onWillUnmount } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { FieldComponent } from "@web/fields/field_component";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class MoleculeViewer3D extends FieldComponent {
    static template = "molecular_screening.MoleculeViewer3D";
    static props = { ...standardFieldProps };

    setup() {
        this.root = elementRef();
        // 3Dmol is ~500 kB: load it only when a compound form is opened.
        onWillStart(() => loadJS("/molecular_screening/static/lib/3dmol/3Dmol-min.js"));
        onMounted(() => this.renderMolecule());
        onPatched(() => this.renderMolecule());
        onWillUnmount(() => this.viewer?.clear());
    }

    get molblock() {
        return this.props.record.data[this.props.name];
    }

    renderMolecule() {
        if (!this.root.el) {
            return;
        }
        const lib = window.$3Dmol || window["3Dmol"];
        if (!this.viewer) {
            this.viewer = lib.createViewer(this.root.el, { backgroundColor: "white" });
        }
        this.viewer.removeAllModels();
        this.viewer.addModel(this.molblock, "sdf");
        this.viewer.setStyle({}, { stick: { radius: 0.15 }, sphere: { scale: 0.25 } });
        this.viewer.zoomTo();
        this.viewer.render();
    }
}

export class MoleculeSvg extends FieldComponent {
    static template = "molecular_screening.MoleculeSvg";
    static props = { ...standardFieldProps };

    get src() {
        const svg = this.props.record.data[this.props.name];
        // Rendered through <img> so any script inside the SVG stays inert.
        return svg ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}` : "";
    }
}

registry.category("fields").add("molecule_viewer_3d", {
    component: MoleculeViewer3D,
    supportedTypes: ["text"],
});
registry.category("fields").add("molecule_svg", {
    component: MoleculeSvg,
    supportedTypes: ["text"],
});
