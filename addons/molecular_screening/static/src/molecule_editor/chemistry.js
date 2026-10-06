/**
 * Valence arithmetic and geometry for the sketch editor.
 *
 * This mirrors tools/valence.py, which is the authority for every stored value;
 * here the same rules run in the browser so the panel answers while you draw.
 * Both are asserted against the same fixtures, so they cannot drift silently.
 */

export const ELEMENTS = {
    H: { weight: 1.008, mono: 1.0078250319, radius: 0.31, valences: [1], group: 1, color: "#8c9aa0" },
    C: { weight: 12.011, mono: 12.0, radius: 0.76, valences: [4], group: 14, color: "#3c4f57" },
    N: { weight: 14.007, mono: 14.0030740052, radius: 0.71, valences: [3, 5], group: 15, color: "#2f6fbf" },
    O: { weight: 15.999, mono: 15.9949146221, radius: 0.66, valences: [2], group: 16, color: "#c0392b" },
    S: { weight: 32.06, mono: 31.97207069, radius: 1.05, valences: [2, 4, 6], group: 16, color: "#c8a415" },
    P: { weight: 30.974, mono: 30.97376151, radius: 1.07, valences: [3, 5], group: 15, color: "#d07c26" },
    F: { weight: 18.998, mono: 18.9984032, radius: 0.57, valences: [1], group: 17, color: "#4b9b5f" },
    Cl: { weight: 35.45, mono: 34.96885271, radius: 1.02, valences: [1, 3, 5, 7], group: 17, color: "#3f8f4c" },
    Br: { weight: 79.904, mono: 78.9183376, radius: 1.2, valences: [1, 3, 5, 7], group: 17, color: "#8a5a2b" },
    I: { weight: 126.904, mono: 126.904473, radius: 1.39, valences: [1, 3, 5, 7], group: 17, color: "#6f4a9b" },
};

export const ELEMENT_ORDER = ["C", "N", "O", "S", "P", "F", "Cl", "Br", "I", "H"];
const SUBSCRIPTS = ["₀", "₁", "₂", "₃", "₄", "₅", "₆", "₇", "₈", "₉"];

export function subscript(value) {
    return String(value)
        .split("")
        .map((digit) => SUBSCRIPTS[Number(digit)])
        .join("");
}

export function effectiveValences(element, charge) {
    if (element === "H") {
        return [Math.max(0, 1 - Math.abs(charge))];
    }
    // Up to group 14 either sign costs a bond; from group 15 on a positive
    // charge buys one (N+ takes four) and a negative charge spends one.
    const data = ELEMENTS[element];
    const shift = data.group <= 14 ? -Math.abs(charge) : charge;
    return data.valences.map((value) => value + shift).filter((value) => value >= 0);
}

/**
 * @param {string} element
 * @param {number} charge
 * @param {number} used sum of the orders of the atom's explicit bonds
 * @returns {{count: number, exceeded: boolean, max: number}} `exceeded` means no
 *      valence fits, and then the count carries no meaning
 */
export function implicitHydrogens(element, charge, used) {
    const options = effectiveValences(element, charge).sort((a, b) => a - b);
    const fit = options.find((value) => value >= used);
    if (fit === undefined) {
        return { count: 0, exceeded: true, max: Math.max(0, ...options) };
    }
    return { count: fit - used, exceeded: false, max: fit };
}

function adjacency(molecule) {
    const map = molecule.atoms.map(() => []);
    molecule.bonds.forEach((bond, index) => {
        map[bond.a].push({ atom: bond.b, order: bond.order, bond: index });
        map[bond.b].push({ atom: bond.a, order: bond.order, bond: index });
    });
    return map;
}

export function usedValence(molecule, index) {
    return adjacency(molecule)[index].reduce((total, link) => total + link.order, 0);
}

function componentCount(molecule) {
    const links = adjacency(molecule);
    const seen = new Set();
    let count = 0;
    molecule.atoms.forEach((_atom, index) => {
        if (seen.has(index)) {
            return;
        }
        count++;
        const stack = [index];
        seen.add(index);
        while (stack.length) {
            for (const link of links[stack.pop()]) {
                if (!seen.has(link.atom)) {
                    seen.add(link.atom);
                    stack.push(link.atom);
                }
            }
        }
    });
    return count;
}

/** A bond is in a ring exactly when it is not a bridge. */
export function ringBonds(molecule) {
    const links = adjacency(molecule);
    const discovery = new Map();
    const low = new Map();
    const inRing = new Set();
    let timer = 0;

    const walk = (node, via) => {
        discovery.set(node, timer);
        low.set(node, timer);
        timer++;
        for (const link of links[node]) {
            if (link.bond === via) {
                continue;
            }
            if (!discovery.has(link.atom)) {
                walk(link.atom, link.bond);
                low.set(node, Math.min(low.get(node), low.get(link.atom)));
                if (low.get(link.atom) <= discovery.get(node)) {
                    inRing.add(link.bond);
                }
            } else {
                low.set(node, Math.min(low.get(node), discovery.get(link.atom)));
                inRing.add(link.bond);
            }
        }
    };

    molecule.atoms.forEach((_atom, index) => {
        if (!discovery.has(index)) {
            walk(index, -1);
        }
    });
    return inRing;
}

const MAX_RING_SIZE = 8;
const AROMATIC_ELEMENTS = ["C", "N", "O", "S", "P"];

function lonePairs(element, charge, used, hydrogens) {
    const group = ELEMENTS[element].group;
    const electrons = (group <= 2 ? group : group === 14 ? 4 : group - 10) - charge - used - hydrogens;
    return Math.max(0, Math.floor(electrons / 2));
}

/** Every simple cycle of at most eight atoms, as a sorted array of bond indices. */
export function smallRings(molecule) {
    const inRing = ringBonds(molecule);
    const links = adjacency(molecule).map((list) => list.filter((link) => inRing.has(link.bond)));
    const found = new Map();
    const walk = (start, node, pathAtoms, pathBonds) => {
        for (const link of links[node]) {
            if (link.atom === start && pathBonds.length >= 2 && !pathBonds.includes(link.bond)) {
                const ring = [...pathBonds, link.bond].sort((a, b) => a - b);
                found.set(ring.join(","), ring);
            } else if (link.atom > start && !pathAtoms.has(link.atom) && pathAtoms.size < MAX_RING_SIZE) {
                walk(start, link.atom, new Set([...pathAtoms, link.atom]), [...pathBonds, link.bond]);
            }
        }
    };
    molecule.atoms.forEach((_atom, index) => walk(index, index, new Set([index]), []));
    return [...found.values()];
}

function piElectrons(molecule, index, links, inRing) {
    const atom = molecule.atoms[index];
    if (!AROMATIC_ELEMENTS.includes(atom.element) || links.some((link) => link.order === 3)) {
        return null;
    }
    const doubles = links.filter((link) => link.order === 2);
    if (doubles.length > 1) {
        return null;
    }
    if (doubles.length) {
        if (inRing.has(doubles[0].bond)) {
            return 1;
        }
        // exocyclic C=O/N/S pulls its electron out (2-pyridone); C=C breaks the ring (fulvene)
        return ["N", "O", "S"].includes(molecule.atoms[doubles[0].atom].element) ? 0 : null;
    }
    if (atom.element === "C") {
        return { 1: 0, "-1": 2 }[atom.charge] ?? null;
    }
    const used = links.reduce((total, link) => total + link.order, 0);
    const hydrogens = implicitHydrogens(atom.element, atom.charge, used);
    if (hydrogens.exceeded || !lonePairs(atom.element, atom.charge, used, hydrogens.count)) {
        return null;
    }
    return 2;
}

/**
 * Hückel 4n+2 perception on rings of up to eight atoms, and on fused pairs that
 * are not aromatic alone. Mirrors valence.aromaticity.
 *
 * @returns {{atoms: Set<number>, bonds: Set<number>, rings: number}}
 */
export function aromaticity(molecule) {
    const links = adjacency(molecule);
    const inRing = ringBonds(molecule);
    const electrons = molecule.atoms.map((_atom, index) =>
        piElectrons(molecule, index, links[index], inRing)
    );
    const ringAtoms = (ring) =>
        new Set(ring.flatMap((bond) => [molecule.bonds[bond].a, molecule.bonds[bond].b]));
    const huckel = (members) => {
        const figures = [...members].map((index) => electrons[index]);
        return !figures.includes(null) && figures.reduce((a, b) => a + b, 0) % 4 === 2;
    };
    const rings = smallRings(molecule);
    const aromatic = rings.filter((ring) => huckel(ringAtoms(ring)));
    const rest = rings.filter((ring) => !aromatic.includes(ring));
    rest.forEach((first, position) => {
        for (const second of rest.slice(position + 1)) {
            const fused = first.some((bond) => second.includes(bond));
            if (fused && huckel(new Set([...ringAtoms(first), ...ringAtoms(second)]))) {
                aromatic.push(...[first, second].filter((ring) => !aromatic.includes(ring)));
            }
        }
    });
    return {
        atoms: new Set(aromatic.flatMap((ring) => [...ringAtoms(ring)])),
        bonds: new Set(aromatic.flat()),
        rings: aromatic.length,
    };
}

/**
 * Give bonds a molblock marks aromatic (type 4) alternating orders, in place.
 * Mirrors valence.kekulize: carbons need a double bond, heteroatoms take one only
 * within their lowest valence.
 */
export function kekulize(molecule, marked) {
    if (!marked.length) {
        return;
    }
    const partners = new Map();
    for (const bond of marked) {
        const { a, b } = molecule.bonds[bond];
        molecule.bonds[bond].order = 1;
        partners.set(a, [...(partners.get(a) || []), { atom: b, bond }]);
        partners.set(b, [...(partners.get(b) || []), { atom: a, bond }]);
    }
    const hasDouble = new Set();
    molecule.bonds.forEach((bond, index) => {
        if (!marked.includes(index) && bond.order === 2) {
            hasDouble.add(bond.a).add(bond.b);
        }
    });
    const used = molecule.atoms.map((_atom, index) => usedValence(molecule, index));
    const canTakeDouble = (index) => {
        const atom = molecule.atoms[index];
        if (hasDouble.has(index)) {
            return false;
        }
        if (atom.element === "C") {
            return !atom.charge;
        }
        const options = effectiveValences(atom.element, atom.charge);
        return options.length > 0 && used[index] + 1 <= Math.min(...options);
    };
    for (const list of partners.values()) {
        list.sort(
            (p, q) =>
                (molecule.atoms[p.atom].element !== "C") - (molecule.atoms[q.atom].element !== "C") ||
                p.atom - q.atom
        );
    }
    const needy = [...partners.keys()]
        .filter((index) => molecule.atoms[index].element === "C" && canTakeDouble(index))
        .sort((p, q) => p - q);
    const matched = new Map();
    const assign = (queue) => {
        if (!queue.length) {
            return true;
        }
        const [index, ...rest] = queue;
        if (matched.has(index)) {
            return assign(rest);
        }
        for (const link of partners.get(index)) {
            if (matched.has(link.atom) || !canTakeDouble(link.atom)) {
                continue;
            }
            matched.set(index, link.bond).set(link.atom, link.bond);
            if (assign(rest)) {
                return true;
            }
            matched.delete(index);
            matched.delete(link.atom);
        }
        return false;
    };
    if (!assign(needy)) {
        throw new Error("The aromatic bonds cannot be written as alternating single and double bonds.");
    }
    for (const bond of new Set(matched.values())) {
        molecule.bonds[bond].order = 2;
    }
}

export function rotatableBonds(molecule) {
    const links = adjacency(molecule);
    const inRing = ringBonds(molecule);
    const heavyDegree = (index) =>
        links[index].filter((link) => molecule.atoms[link.atom].element !== "H").length;
    const isAmide = (nitrogen, carbon) =>
        molecule.atoms[nitrogen].element === "N" &&
        molecule.atoms[carbon].element === "C" &&
        links[carbon].some(
            (link) => link.order === 2 && molecule.atoms[link.atom].element === "O"
        );

    let count = 0;
    molecule.bonds.forEach((bond, index) => {
        if (bond.order !== 1 || inRing.has(index)) {
            return;
        }
        if (molecule.atoms[bond.a].element === "H" || molecule.atoms[bond.b].element === "H") {
            return;
        }
        if (heavyDegree(bond.a) < 2 || heavyDegree(bond.b) < 2) {
            return;
        }
        if (isAmide(bond.a, bond.b) || isAmide(bond.b, bond.a)) {
            return;
        }
        count++;
    });
    return count;
}

export function hillFormula(counts) {
    const symbols = ["C", "H"].concat(
        Object.keys(counts)
            .filter((symbol) => symbol !== "C" && symbol !== "H")
            .sort()
    );
    return symbols
        .filter((symbol) => counts[symbol])
        .map((symbol) => symbol + (counts[symbol] > 1 ? subscript(counts[symbol]) : ""))
        .join("");
}

/**
 * Every published figure of a drawn molecule.
 *
 * @param {{atoms: Array, bonds: Array}} molecule
 * @returns {object} masses are null when a valence is exceeded, so the panel
 *      shows a dash rather than a number the table cannot support
 */
export function analyse(molecule) {
    const links = adjacency(molecule);
    const counts = {};
    const exceeded = [];
    let weight = 0;
    let mono = 0;
    let charge = 0;
    let implicitTotal = 0;

    molecule.atoms.forEach((atom, index) => {
        const data = ELEMENTS[atom.element];
        counts[atom.element] = (counts[atom.element] || 0) + 1;
        weight += data.weight;
        mono += data.mono;
        charge += atom.charge;
        const used = links[index].reduce((total, link) => total + link.order, 0);
        const hydrogens = implicitHydrogens(atom.element, atom.charge, used);
        if (hydrogens.exceeded) {
            exceeded.push({ index, element: atom.element, used, max: hydrogens.max });
        } else if (hydrogens.count) {
            implicitTotal += hydrogens.count;
            counts.H = (counts.H || 0) + hydrogens.count;
            weight += ELEMENTS.H.weight * hydrogens.count;
            mono += ELEMENTS.H.mono * hydrogens.count;
        }
    });

    const rings = molecule.atoms.length
        ? Math.max(0, molecule.bonds.length - molecule.atoms.length + componentCount(molecule))
        : 0;
    const piBonds = molecule.bonds.reduce((total, bond) => total + bond.order - 1, 0);

    return {
        formula: hillFormula(counts),
        counts,
        weight: exceeded.length ? null : weight,
        monoisotopic: exceeded.length ? null : mono,
        charge,
        implicitH: implicitTotal,
        rings,
        aromaticRings: molecule.bonds.length ? aromaticity(molecule).rings : 0,
        piBonds,
        unsaturation: rings + piBonds,
        heavyAtoms: molecule.atoms.filter((atom) => atom.element !== "H").length,
        bondCount: molecule.bonds.length,
        rotatableBonds: molecule.bonds.length ? rotatableBonds(molecule) : 0,
        exceeded,
    };
}

/* ------------------------------------------------------------------ molfile */

const SKETCH_SCALE = 38; // canvas pixels per ångström-ish unit

export function toMolblock(molecule, { title = "molecular-screening", origin } = {}) {
    const centre = origin || { x: 0, y: 0 };
    const atoms = molecule.atoms.map((atom) => ({
        element: atom.element,
        formal_charge: atom.charge,
        x: (atom.x - centre.x) / SKETCH_SCALE,
        y: (centre.y - atom.y) / SKETCH_SCALE,
        z: 0,
    }));
    return writeMolblock(atoms, molecule.bonds.map((bond) => ({ ...bond })), title, "2D");
}

export function writeMolblock(atoms, bonds, title, dimension) {
    const pad = (value, width) => String(value).padStart(width);
    const lines = [title, `  molecular_screening      ${dimension}`, ""];
    lines.push(`${pad(atoms.length, 3)}${pad(bonds.length, 3)}  0  0  0  0  0  0  0  0999 V2000`);
    for (const atom of atoms) {
        const coordinates = ["x", "y", "z"]
            .map((axis) => (atom[axis] || 0).toFixed(4).padStart(10))
            .join("");
        lines.push(`${coordinates} ${atom.element.padEnd(3)} 0  0  0  0  0  0  0  0  0  0  0  0`);
    }
    for (const bond of bonds) {
        const a = bond.atom_a ?? bond.a + 1;
        const b = bond.atom_b ?? bond.b + 1;
        lines.push(`${pad(a, 3)}${pad(b, 3)}${pad(bond.order || bond.bond_order, 3)}  0`);
    }
    const charged = atoms
        .map((atom, index) => [index + 1, atom.formal_charge || 0])
        .filter(([, charge]) => charge);
    for (let start = 0; start < charged.length; start += 8) {
        const chunk = charged.slice(start, start + 8);
        lines.push(
            `M  CHG${pad(chunk.length, 3)}` +
                chunk.map(([index, charge]) => `${pad(index, 4)}${pad(charge, 4)}`).join("")
        );
    }
    lines.push("M  END");
    return lines.join("\n") + "\n";
}

/**
 * Read a V2000 molblock back into the sketch model.
 *
 * @param {string} molblock
 * @param {{width: number, height: number}} viewport used to lay 3D input flat
 * @returns {{atoms: Array, bonds: Array}}
 */
export function fromMolblock(molblock, viewport = { width: 600, height: 440 }) {
    const lines = (molblock || "").replace(/\r\n/g, "\n").split("\n");
    if (lines.length < 4 || !lines[3].includes("V2000")) {
        throw new Error("Only V2000 molblocks are supported.");
    }
    const atomCount = parseInt(lines[3].slice(0, 3), 10);
    const bondCount = parseInt(lines[3].slice(3, 6), 10);
    if (!Number.isFinite(atomCount) || !Number.isFinite(bondCount)) {
        throw new Error("Malformed counts line.");
    }
    const raw = [];
    for (let i = 0; i < atomCount; i++) {
        const line = lines[4 + i] || "";
        raw.push({
            element: line.slice(31, 34).trim() || "C",
            x: parseFloat(line.slice(0, 10)),
            y: parseFloat(line.slice(10, 20)),
            charge: 0,
        });
    }
    const bonds = [];
    const marked = [];
    for (let i = 0; i < bondCount; i++) {
        const line = lines[4 + atomCount + i] || "";
        const a = parseInt(line.slice(0, 3), 10) - 1;
        const b = parseInt(line.slice(3, 6), 10) - 1;
        const order = parseInt(line.slice(6, 9), 10) || 1;
        if (order === 4) {
            marked.push(i);
        }
        bonds.push({ a: Math.min(a, b), b: Math.max(a, b), order: order === 4 ? 1 : order });
    }
    for (const line of lines.slice(4 + atomCount + bondCount)) {
        if (line.startsWith("M  CHG")) {
            const fields = line.trim().split(/\s+/).slice(3);
            for (let i = 0; i < fields.length; i += 2) {
                const index = parseInt(fields[i], 10) - 1;
                if (raw[index]) {
                    raw[index].charge = parseInt(fields[i + 1], 10);
                }
            }
        } else if (line.startsWith("M  END")) {
            break;
        }
    }
    // Fit whatever coordinate system the file used into the canvas
    const xs = raw.map((atom) => atom.x).filter(Number.isFinite);
    const ys = raw.map((atom) => atom.y).filter(Number.isFinite);
    const spanX = Math.max(...xs) - Math.min(...xs) || 1;
    const spanY = Math.max(...ys) - Math.min(...ys) || 1;
    const scale = Math.min(
        SKETCH_SCALE,
        (viewport.width - 120) / spanX,
        (viewport.height - 120) / spanY
    );
    const midX = (Math.max(...xs) + Math.min(...xs)) / 2 || 0;
    const midY = (Math.max(...ys) + Math.min(...ys)) / 2 || 0;
    const atoms = raw.map((atom) => ({
        element: atom.element,
        charge: atom.charge,
        x: viewport.width / 2 + ((Number.isFinite(atom.x) ? atom.x : 0) - midX) * scale,
        y: viewport.height / 2 - ((Number.isFinite(atom.y) ? atom.y : 0) - midY) * scale,
    }));
    const molecule = { atoms, bonds };
    kekulize(molecule, marked);
    return molecule;
}

/* ------------------------------------------------------------- 3D geometry */

function bondTarget(model, bond) {
    const ra = ELEMENTS[model.atoms[bond.a].element].radius;
    const rb = ELEMENTS[model.atoms[bond.b].element].radius;
    const shrink = bond.order === 3 ? 0.8 : bond.order === 2 ? 0.88 : 1;
    return (ra + rb) * shrink;
}

/** sp from a triple bond or two doubles, sp2 from one double, sp3 otherwise. */
function targetAngle(model, centre) {
    const attached = model.bonds.filter((bond) => bond.a === centre || bond.b === centre);
    const maxOrder = attached.reduce((best, bond) => Math.max(best, bond.order), 1);
    const doubles = attached.filter((bond) => bond.order === 2).length;
    if (maxOrder === 3 || doubles >= 2) {
        return Math.PI;
    }
    if (maxOrder === 2) {
        return (120 * Math.PI) / 180;
    }
    return (109.5 * Math.PI) / 180;
}

/**
 * Build the 3D model of a sketch, implicit hydrogens made explicit.
 *
 * Without the hydrogens benzene relaxes as a bare ring and the picture stops
 * matching the formula.
 */
export function buildModel(molecule, seed = 1) {
    const atoms = [];
    const bonds = [];
    const jitter = (() => {
        let value = seed;
        return () => {
            value = (value * 16807) % 2147483647;
            return value / 2147483647 - 0.5;
        };
    })();

    molecule.atoms.forEach((atom) => {
        atoms.push({
            element: atom.element,
            charge: atom.charge,
            x: atom.x / SKETCH_SCALE,
            y: -atom.y / SKETCH_SCALE,
            z: jitter() * 0.4,
        });
    });
    molecule.bonds.forEach((bond) => bonds.push({ a: bond.a, b: bond.b, order: bond.order }));

    molecule.atoms.forEach((atom, index) => {
        const used = usedValence(molecule, index);
        const hydrogens = implicitHydrogens(atom.element, atom.charge, used);
        if (hydrogens.exceeded) {
            return;
        }
        for (let k = 0; k < hydrogens.count; k++) {
            const angle = (k / Math.max(1, hydrogens.count)) * Math.PI * 2 + index;
            atoms.push({
                element: "H",
                charge: 0,
                x: atom.x / SKETCH_SCALE + Math.cos(angle) * 0.9,
                y: -atom.y / SKETCH_SCALE + Math.sin(angle) * 0.9,
                z: jitter() * 0.6,
            });
            bonds.push({ a: index, b: atoms.length - 1, order: 1 });
        }
    });

    return { atoms, bonds };
}

const sub = (p, q) => [p[0] - q[0], p[1] - q[1], p[2] - q[2]];
const norm = (v) => Math.hypot(v[0], v[1], v[2]);
const scale = (v, k) => [v[0] * k, v[1] * k, v[2] * k];
const dot = (u, v) => u[0] * v[0] + u[1] * v[1] + u[2] * v[2];
const cross = (u, v) => [
    u[1] * v[2] - u[2] * v[1],
    u[2] * v[0] - u[0] * v[2],
    u[0] * v[1] - u[1] * v[0],
];

/**
 * Relax a model: bond springs, angle terms by hybridisation, repulsion between
 * atoms three bonds apart or more, and a planarity term at sp2 centres.
 *
 * @returns {{steps: number, force: number}} what it took to settle, so the
 *      result is reported rather than presented as converged by assertion
 */
export function relax(model, steps = 900) {
    const n = model.atoms.length;
    if (!n) {
        return { steps: 0, force: 0 };
    }
    const positions = model.atoms.map((atom) => [atom.x, atom.y, atom.z]);
    const links = model.atoms.map(() => new Set());
    model.bonds.forEach((bond) => {
        links[bond.a].add(bond.b);
        links[bond.b].add(bond.a);
    });

    const far = [];
    for (let i = 0; i < n; i++) {
        const distance = new Array(n).fill(Infinity);
        distance[i] = 0;
        const queue = [i];
        while (queue.length) {
            const current = queue.shift();
            if (distance[current] >= 2) {
                continue;
            }
            for (const next of links[current]) {
                if (distance[next] === Infinity) {
                    distance[next] = distance[current] + 1;
                    queue.push(next);
                }
            }
        }
        for (let j = i + 1; j < n; j++) {
            if (distance[j] > 2) {
                far.push([i, j]);
            }
        }
    }

    const angles = [];
    const planar = [];
    for (let centre = 0; centre < n; centre++) {
        const list = [...links[centre]];
        const ideal = list.length >= 4 ? (109.5 * Math.PI) / 180 : targetAngle(model, centre);
        for (let i = 0; i < list.length; i++) {
            for (let j = i + 1; j < list.length; j++) {
                angles.push([list[i], centre, list[j], ideal]);
            }
        }
        if (list.length === 3 && targetAngle(model, centre) === (120 * Math.PI) / 180) {
            planar.push([centre, ...list]);
        }
    }

    let step = 0.05;
    let maxForce = 0;
    let used = steps;

    for (let iteration = 0; iteration < steps; iteration++) {
        const force = Array.from({ length: n }, () => [0, 0, 0]);

        for (const bond of model.bonds) {
            const target = bondTarget(model, bond);
            const delta = sub(positions[bond.b], positions[bond.a]);
            const length = norm(delta) || 1e-6;
            const k = (3.2 * (length - target)) / length;
            for (let axis = 0; axis < 3; axis++) {
                force[bond.a][axis] += k * delta[axis];
                force[bond.b][axis] -= k * delta[axis];
            }
        }

        for (const [i, centre, j, ideal] of angles) {
            const u = sub(positions[i], positions[centre]);
            const v = sub(positions[j], positions[centre]);
            const lu = norm(u) || 1e-6;
            const lv = norm(v) || 1e-6;
            const cosine = Math.max(-0.9999, Math.min(0.9999, dot(u, v) / (lu * lv)));
            const sine = Math.sqrt(1 - cosine * cosine) || 1e-6;
            const error = Math.acos(cosine) - ideal;
            const gi = scale(sub(scale(u, cosine / lu), scale(v, 1 / lv)), 1 / (lu * sine));
            const gj = scale(sub(scale(v, cosine / lv), scale(u, 1 / lu)), 1 / (lv * sine));
            const k = 0.9 * error;
            for (let axis = 0; axis < 3; axis++) {
                force[i][axis] -= k * gi[axis];
                force[j][axis] -= k * gj[axis];
                force[centre][axis] += k * (gi[axis] + gj[axis]);
            }
        }

        for (const [i, j] of far) {
            const delta = sub(positions[j], positions[i]);
            const length = norm(delta) || 1e-6;
            if (length > 3.6) {
                continue;
            }
            const k = 0.55 / length ** 3;
            for (let axis = 0; axis < 3; axis++) {
                force[i][axis] -= k * delta[axis];
                force[j][axis] += k * delta[axis];
            }
        }

        for (const [centre, p, q, r] of planar) {
            const normal = cross(sub(positions[q], positions[p]), sub(positions[r], positions[p]));
            const length = norm(normal) || 1e-6;
            const unit = scale(normal, 1 / length);
            const offset = dot(sub(positions[centre], positions[p]), unit);
            for (let axis = 0; axis < 3; axis++) {
                force[centre][axis] -= 1.4 * offset * unit[axis];
                force[p][axis] += 0.47 * offset * unit[axis];
                force[q][axis] += 0.47 * offset * unit[axis];
                force[r][axis] += 0.47 * offset * unit[axis];
            }
        }

        maxForce = 0;
        for (let i = 0; i < n; i++) {
            maxForce = Math.max(maxForce, norm(force[i]));
            for (let axis = 0; axis < 3; axis++) {
                positions[i][axis] += step * force[i][axis];
            }
        }
        step = Math.max(0.012, step * 0.9995);
        if (maxForce < 2e-3) {
            used = iteration + 1;
            break;
        }
    }

    const centre = [0, 1, 2].map(
        (axis) => positions.reduce((total, position) => total + position[axis], 0) / n
    );
    model.atoms.forEach((atom, index) => {
        atom.x = positions[index][0] - centre[0];
        atom.y = positions[index][1] - centre[1];
        atom.z = positions[index][2] - centre[2];
    });
    return { steps: used, force: maxForce };
}

export function modelToMolblock(model, title = "relaxed") {
    const atoms = model.atoms.map((atom) => ({
        element: atom.element,
        formal_charge: atom.charge,
        x: atom.x,
        y: atom.y,
        z: atom.z,
    }));
    return writeMolblock(atoms, model.bonds, title, "3D");
}
