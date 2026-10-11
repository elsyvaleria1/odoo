import { onMounted, onWillUnmount, proxy } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { FieldComponent } from "@web/fields/field_component";
import { useRecordObserver } from "@web/fields/hooks/record_observer";
import { standardFieldProps } from "@web/fields/standard_field_props";

import {
    analyse,
    buildModel,
    ELEMENT_ORDER,
    ELEMENTS,
    fromMolblock,
    implicitHydrogens,
    modelToMolblock,
    relax,
    subscript,
    toMolblock,
    usedValence,
} from "./chemistry.js";

const ATOM_HIT = 18;
const BOND_HIT = 10;
const MODES = ["draw", "erase", "plus", "minus"];

export class MoleculeEditor extends FieldComponent {
    static template = "molecular_screening.MoleculeEditor";
    static props = { ...standardFieldProps };

    setup() {
        this.canvasRef = elementRef();
        this.viewerRef = elementRef();
        this.elements = ELEMENT_ORDER;
        this.state = proxy({
            element: "C",
            mode: "draw",
            spheres: false,
            relaxNote: "",
            info: null,
        });
        this.molecule = { atoms: [], bonds: [] };
        this.selected = null;
        this.hover = null;
        this.drag = null;
        this.model3d = null;
        this.viewer = null;
        this.libraryReady = loadJS(
            "/molecular_screening/static/lib/3dmol/3Dmol-min.js",
        ).catch(() => false);

        useRecordObserver((record, props) => {
            const incoming = record.data[props.name];
            if (incoming !== this.lastWritten) {
                this.loadFromRecord(incoming);
                this.redraw();
            }
        });
        onMounted(() => {
            this.resizeObserver = new ResizeObserver(() => this.redraw());
            this.resizeObserver.observe(this.canvasRef.el);
            this.redraw();
        });
        onWillUnmount(() => {
            this.resizeObserver?.disconnect();
            this.viewer?.clear();
        });
        useLayoutEffect(
            () => this.redraw(),
            () => [this.state.mode, this.state.element],
        );
    }

    get readonly() {
        return this.props.readonly;
    }

    get viewport() {
        const element = this.canvasRef.el;
        return {
            width: element ? element.clientWidth : 620,
            height: element ? element.clientHeight : 440,
        };
    }

    loadFromRecord(molblock) {
        if (!molblock) {
            this.molecule = { atoms: [], bonds: [] };
        } else {
            try {
                this.molecule = fromMolblock(molblock, this.viewport);
            } catch {
                this.molecule = { atoms: [], bonds: [] };
                this.state.relaxNote = _t("This structure could not be drawn here.");
            }
        }
        this.selected = null;
        this.model3d = null;
        this.state.info = analyse(this.molecule);
    }

    commit() {
        this.state.info = analyse(this.molecule);
        if (this.readonly) {
            return;
        }
        const centre = { x: this.viewport.width / 2, y: this.viewport.height / 2 };
        const molblock = this.molecule.atoms.length
            ? toMolblock(this.molecule, { origin: centre })
            : false;
        this.lastWritten = molblock;
        this.props.record.update({ [this.props.name]: molblock });
    }

    selectElement(symbol) {
        this.state.element = symbol;
    }

    selectMode(mode) {
        this.state.mode = mode;
        this.selected = null;
    }

    get modeHint() {
        const hints = {
            draw: _t(
                "Click empty space for an atom, two atoms for a bond, a bond to cycle single → double → triple. Drag to move.",
            ),
            erase: _t("Click an atom or a bond to remove it."),
            plus: _t("Click an atom to raise its formal charge."),
            minus: _t("Click an atom to lower its formal charge."),
        };
        return hints[this.state.mode];
    }

    modeLabel(mode) {
        return {
            draw: _t("Draw"),
            erase: _t("Erase"),
            plus: _t("Charge +"),
            minus: _t("Charge −"),
        }[mode];
    }

    get modes() {
        return MODES;
    }

    loadSample(which) {
        if (which === "benzene") {
            const centre = { x: this.viewport.width / 2, y: this.viewport.height / 2 };
            const radius = 78;
            this.molecule = { atoms: [], bonds: [] };
            for (let i = 0; i < 6; i++) {
                const angle = (Math.PI / 3) * i - Math.PI / 2;
                this.molecule.atoms.push({
                    element: "C",
                    x: centre.x + radius * Math.cos(angle),
                    y: centre.y + radius * Math.sin(angle),
                    charge: 0,
                });
            }
            for (let i = 0; i < 6; i++) {
                this.molecule.bonds.push({
                    a: Math.min(i, (i + 1) % 6),
                    b: Math.max(i, (i + 1) % 6),
                    order: i % 2 === 0 ? 2 : 1,
                });
            }
        } else if (which === "acetonitrile") {
            const centre = { x: this.viewport.width / 2, y: this.viewport.height / 2 };
            this.molecule = {
                atoms: [
                    { element: "C", x: centre.x - 90, y: centre.y, charge: 0 },
                    { element: "C", x: centre.x, y: centre.y, charge: 0 },
                    { element: "N", x: centre.x + 90, y: centre.y, charge: 0 },
                ],
                bonds: [
                    { a: 0, b: 1, order: 1 },
                    { a: 1, b: 2, order: 3 },
                ],
            };
        } else {
            this.molecule = { atoms: [], bonds: [] };
            this.state.relaxNote = "";
            this.viewer?.removeAllModels();
            this.viewer?.render();
        }
        this.selected = null;
        this.model3d = null;
        this.commit();
        this.redraw();
    }

    pointerPosition(event) {
        const rect = this.canvasRef.el.getBoundingClientRect();
        return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }

    atomAt(x, y) {
        for (let i = this.molecule.atoms.length - 1; i >= 0; i--) {
            const atom = this.molecule.atoms[i];
            if ((atom.x - x) ** 2 + (atom.y - y) ** 2 <= ATOM_HIT ** 2) {
                return i;
            }
        }
        return -1;
    }

    bondAt(x, y) {
        for (let i = 0; i < this.molecule.bonds.length; i++) {
            const bond = this.molecule.bonds[i];
            const pa = this.molecule.atoms[bond.a];
            const pb = this.molecule.atoms[bond.b];
            const vx = pb.x - pa.x;
            const vy = pb.y - pa.y;
            const length = vx * vx + vy * vy;
            if (!length) {
                continue;
            }
            const t = ((x - pa.x) * vx + (y - pa.y) * vy) / length;
            if (t < 0.22 || t > 0.78) {
                continue;
            }
            const px = pa.x + t * vx;
            const py = pa.y + t * vy;
            if ((px - x) ** 2 + (py - y) ** 2 <= BOND_HIT ** 2) {
                return i;
            }
        }
        return -1;
    }

    onPointerDown(event) {
        if (this.readonly) {
            return;
        }
        this.canvasRef.el.setPointerCapture(event.pointerId);
        const point = this.pointerPosition(event);
        const index = this.atomAt(point.x, point.y);
        this.drag =
            index >= 0 && this.state.mode === "draw"
                ? { index, moved: false, from: point }
                : null;
    }

    onPointerMove(event) {
        if (this.readonly) {
            return;
        }
        const point = this.pointerPosition(event);
        if (this.drag) {
            if (
                Math.hypot(point.x - this.drag.from.x, point.y - this.drag.from.y) > 4
            ) {
                this.drag.moved = true;
                const atom = this.molecule.atoms[this.drag.index];
                atom.x = point.x;
                atom.y = point.y;
                this.model3d = null;
                this.redraw();
            }
            return;
        }
        const atomIndex = this.atomAt(point.x, point.y);
        const bondIndex = atomIndex >= 0 ? -1 : this.bondAt(point.x, point.y);
        const next =
            atomIndex >= 0
                ? { type: "atom", index: atomIndex }
                : bondIndex >= 0
                  ? { type: "bond", index: bondIndex }
                  : null;
        if (JSON.stringify(next) !== JSON.stringify(this.hover)) {
            this.hover = next;
            this.redraw();
        }
    }

    onPointerUp(event) {
        if (this.readonly) {
            return;
        }
        const point = this.pointerPosition(event);
        const dragged = this.drag?.moved;
        const dragIndex = this.drag?.index;
        this.drag = null;
        if (dragged) {
            this.commit();
            return;
        }

        const atomIndex = dragIndex ?? this.atomAt(point.x, point.y);
        const bondIndex = atomIndex >= 0 ? -1 : this.bondAt(point.x, point.y);

        if (this.state.mode === "erase") {
            if (atomIndex >= 0) {
                this.removeAtom(atomIndex);
            } else if (bondIndex >= 0) {
                this.molecule.bonds.splice(bondIndex, 1);
            }
        } else if (this.state.mode === "plus" || this.state.mode === "minus") {
            if (atomIndex >= 0) {
                const atom = this.molecule.atoms[atomIndex];
                const delta = this.state.mode === "plus" ? 1 : -1;
                atom.charge = Math.max(-3, Math.min(3, atom.charge + delta));
            }
        } else if (atomIndex >= 0) {
            if (this.selected === null) {
                this.selected = atomIndex;
            } else if (this.selected === atomIndex) {
                this.selected = null;
            } else {
                this.addBond(this.selected, atomIndex);
                this.selected = null;
            }
        } else if (bondIndex >= 0) {
            this.cycleBond(bondIndex);
        } else {
            this.molecule.atoms.push({
                element: this.state.element,
                x: point.x,
                y: point.y,
                charge: 0,
            });
            this.selected = null;
        }
        this.model3d = null;
        this.commit();
        this.redraw();
    }

    onPointerLeave() {
        this.hover = null;
        this.redraw();
    }

    removeAtom(index) {
        this.molecule.bonds = this.molecule.bonds
            .filter((bond) => bond.a !== index && bond.b !== index)
            .map((bond) => ({
                a: bond.a > index ? bond.a - 1 : bond.a,
                b: bond.b > index ? bond.b - 1 : bond.b,
                order: bond.order,
            }));
        this.molecule.atoms.splice(index, 1);
        this.selected = null;
    }

    addBond(a, b) {
        const lo = Math.min(a, b);
        const hi = Math.max(a, b);
        const existing = this.molecule.bonds.findIndex(
            (bond) => bond.a === lo && bond.b === hi,
        );
        if (existing >= 0) {
            this.cycleBond(existing);
            return;
        }
        this.molecule.bonds.push({ a: lo, b: hi, order: 1 });
    }

    cycleBond(index) {
        const bond = this.molecule.bonds[index];
        bond.order = bond.order === 3 ? 1 : bond.order + 1;
    }

    themeColor(name) {
        return (
            getComputedStyle(this.canvasRef.el).getPropertyValue(name).trim() || "#000"
        );
    }

    redraw() {
        const canvas = this.canvasRef.el;
        if (!canvas) {
            return;
        }
        const ratio = window.devicePixelRatio || 1;
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        const ctx = canvas.getContext("2d");
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

        const ink = this.themeColor("--MoleculeEditor-ink") || "#17252b";
        const accent = this.themeColor("--MoleculeEditor-accent") || "#0d7680";
        const alert = this.themeColor("--MoleculeEditor-alert") || "#a3322a";
        const paper = this.themeColor("--MoleculeEditor-paper") || "#ffffff";
        const grid = this.themeColor("--MoleculeEditor-grid") || "rgba(0,0,0,.06)";

        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = paper;
        ctx.fillRect(0, 0, width, height);
        ctx.strokeStyle = grid;
        ctx.lineWidth = 1;
        for (let x = 24; x < width; x += 24) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, height);
            ctx.stroke();
        }
        for (let y = 24; y < height; y += 24) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(width, y);
            ctx.stroke();
        }

        this.molecule.bonds.forEach((bond, index) => {
            const pa = this.molecule.atoms[bond.a];
            const pb = this.molecule.atoms[bond.b];
            if (!pa || !pb) {
                return;
            }
            const dx = pb.x - pa.x;
            const dy = pb.y - pa.y;
            const length = Math.hypot(dx, dy) || 1;
            const ux = dx / length;
            const uy = dy / length;
            const nx = -uy;
            const ny = ux;
            const gap = 3.4;
            const trim = 15;
            const offsets =
                bond.order === 1
                    ? [0]
                    : bond.order === 2
                      ? [-gap, gap]
                      : [-gap * 1.9, 0, gap * 1.9];
            ctx.strokeStyle =
                this.hover?.type === "bond" && this.hover.index === index
                    ? accent
                    : ink;
            ctx.lineWidth = 1.9;
            ctx.lineCap = "round";
            for (const offset of offsets) {
                ctx.beginPath();
                ctx.moveTo(
                    pa.x + ux * trim + nx * offset,
                    pa.y + uy * trim + ny * offset,
                );
                ctx.lineTo(
                    pb.x - ux * trim + nx * offset,
                    pb.y - uy * trim + ny * offset,
                );
                ctx.stroke();
            }
        });

        this.molecule.atoms.forEach((atom, index) => {
            const used = usedValence(this.molecule, index);
            const hydrogens = implicitHydrogens(atom.element, atom.charge, used);
            let label = atom.element;
            if (!hydrogens.exceeded && hydrogens.count > 0) {
                label += "H" + (hydrogens.count > 1 ? subscript(hydrogens.count) : "");
            }
            ctx.font = "500 15px system-ui, sans-serif";
            const radius = Math.max(13, ctx.measureText(label).width / 2 + 5);

            ctx.beginPath();
            ctx.arc(atom.x, atom.y, radius, 0, Math.PI * 2);
            ctx.fillStyle = paper;
            ctx.fill();
            if (
                hydrogens.exceeded ||
                this.selected === index ||
                (this.hover?.type === "atom" && this.hover.index === index)
            ) {
                ctx.lineWidth = 2;
                ctx.strokeStyle = hydrogens.exceeded ? alert : accent;
                ctx.stroke();
            }

            ctx.fillStyle = ELEMENTS[atom.element]?.color || ink;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(label, atom.x, atom.y + 0.5);

            if (atom.charge) {
                ctx.font = "600 11px monospace";
                ctx.fillStyle = atom.charge > 0 ? accent : alert;
                ctx.textAlign = "left";
                const magnitude =
                    Math.abs(atom.charge) > 1 ? Math.abs(atom.charge) : "";
                ctx.fillText(
                    `${magnitude}${atom.charge > 0 ? "+" : "−"}`,
                    atom.x + radius - 2,
                    atom.y - radius + 4,
                );
            }
        });
    }

    async relaxGeometry() {
        if (!this.molecule.atoms.length) {
            return;
        }
        const model = buildModel(this.molecule);
        const result = relax(model);
        this.model3d = model;
        this.state.relaxNote = _t(
            "%(atoms)s atoms with explicit H · %(steps)s steps · max force %(force)s. Approximate geometry, not docking quality.",
            {
                atoms: model.atoms.length,
                steps: result.steps,
                force: result.force.toFixed(4),
            },
        );
        await this.showViewer();
    }

    async showViewer() {
        await this.libraryReady;
        const library = window.$3Dmol || window["3Dmol"];
        if (!library || !this.model3d || !this.viewerRef.el) {
            return;
        }
        const background = this.themeColor("--MoleculeEditor-paper") || "#ffffff";
        if (!this.viewer) {
            this.viewer = library.createViewer(this.viewerRef.el, {
                backgroundColor: background,
            });
        }
        this.viewer.setBackgroundColor(background);
        this.viewer.removeAllModels();
        this.viewer.addModel(modelToMolblock(this.model3d), "sdf");
        this.viewer.setStyle(
            {},
            this.state.spheres
                ? { sphere: { scale: 0.32 }, stick: { radius: 0.1 } }
                : { stick: { radius: 0.14 } },
        );
        this.viewer.zoomTo();
        this.viewer.render();
    }

    toggleStyle() {
        this.state.spheres = !this.state.spheres;
        this.showViewer();
    }

    useRelaxed() {
        if (!this.model3d || !this.hasRelaxedTarget) {
            return;
        }
        this.props.record.update({
            molblock_3d: modelToMolblock(this.model3d, "relaxed"),
        });
    }

    get hasRelaxedTarget() {
        return "molblock_3d" in this.props.record.data;
    }

    formatMass(value, digits) {
        return value === null || value === undefined ? "—" : value.toFixed(digits);
    }
}

export const moleculeEditorField = {
    component: MoleculeEditor,
    displayName: _t("Molecule Editor"),
    supportedTypes: ["text"],
};

registry.category("fields").add("molecule_editor", moleculeEditorField);
