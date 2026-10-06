"""Valence arithmetic over a connection table.

This is the authority for every stored number: the editor's live panel mirrors
these rules in JavaScript for immediate feedback, and both are asserted against
the same fixtures so the two cannot drift silently.

Aromaticity is perceived by Hückel's rule on small rings; nothing here perceives
stereochemistry, and nothing here is a substitute for a chemistry toolkit.
"""

# Standard atomic weights (IUPAC 2021) and the mass of the most abundant isotope
WEIGHTS = {
    "H": 1.008,
    "C": 12.011,
    "N": 14.007,
    "O": 15.999,
    "S": 32.06,
    "P": 30.974,
    "F": 18.998,
    "Cl": 35.45,
    "Br": 79.904,
    "I": 126.904,
}
MONOISOTOPIC = {
    "H": 1.0078250319,
    "C": 12.0,
    "N": 14.0030740052,
    "O": 15.9949146221,
    "S": 31.97207069,
    "P": 30.97376151,
    "F": 18.99840320,
    "Cl": 34.96885271,
    "Br": 78.9183376,
    "I": 126.904473,
}
# Single-bond covalent radii, Cordero et al. (2008), in ångström
RADII = {
    "H": 0.31,
    "C": 0.76,
    "N": 0.71,
    "O": 0.66,
    "S": 1.05,
    "P": 1.07,
    "F": 0.57,
    "Cl": 1.02,
    "Br": 1.20,
    "I": 1.39,
}
VALENCES = {
    "H": (1,),
    "C": (4,),
    "N": (3, 5),
    "O": (2,),
    "S": (2, 4, 6),
    "P": (3, 5),
    "F": (1,),
    "Cl": (1, 3, 5, 7),
    "Br": (1, 3, 5, 7),
    "I": (1, 3, 5, 7),
}
GROUPS = {
    "H": 1,
    "C": 14,
    "N": 15,
    "P": 15,
    "O": 16,
    "S": 16,
    "F": 17,
    "Cl": 17,
    "Br": 17,
    "I": 17,
}
METHOD = "valence-table-v1"


def effective_valences(element, charge):
    """Return the valences ``element`` can take carrying ``charge``.

    :param str element: element symbol
    :param int charge: formal charge
    :rtype: list[int]
    """
    if element == "H":
        return [max(0, 1 - abs(charge))]
    # Up to group 14 either sign costs a bond; from group 15 on a positive
    # charge buys one (N+ takes four) and a negative charge spends one.
    shift = -abs(charge) if GROUPS.get(element, 14) <= 14 else charge
    return [value + shift for value in VALENCES[element] if value + shift >= 0]


def implicit_hydrogens(element, charge, used):
    """Return how many hydrogens complete an atom's valence.

    :param str element: element symbol
    :param int charge: formal charge
    :param int used: sum of the orders of the atom's explicit bonds
    :return: ``(count, exceeded)``; ``exceeded`` means no valence fits, and then
        the count is meaningless and must not be published as a number
    :rtype: tuple[int, bool]
    """
    options = sorted(effective_valences(element, charge))
    fit = next((value for value in options if value >= used), None)
    if fit is None:
        return 0, True
    return fit - used, False


def _neighbours(atoms, bonds):
    adjacency = {atom["idx"]: [] for atom in atoms}
    for bond in bonds:
        adjacency[bond["atom_a"]].append((bond["atom_b"], bond["bond_order"]))
        adjacency[bond["atom_b"]].append((bond["atom_a"], bond["bond_order"]))
    return adjacency


def _components(atoms, adjacency):
    seen, count = set(), 0
    for atom in atoms:
        if atom["idx"] in seen:
            continue
        count += 1
        stack = [atom["idx"]]
        seen.add(atom["idx"])
        while stack:
            for neighbour, _order in adjacency[stack.pop()]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
    return count


def ring_bonds(atoms, bonds):
    """Return the indices of the bonds that sit in a ring.

    A bond is in a ring exactly when it is not a bridge, so the answer comes
    from one low-link pass and needs no ring perception.

    :rtype: set[int]
    """
    adjacency = {atom["idx"]: [] for atom in atoms}
    for position, bond in enumerate(bonds):
        adjacency[bond["atom_a"]].append((bond["atom_b"], position))
        adjacency[bond["atom_b"]].append((bond["atom_a"], position))
    discovery, low, in_ring, timer = {}, {}, set(), 0

    def walk(node, via):
        nonlocal timer
        discovery[node] = low[node] = timer
        timer += 1
        for neighbour, position in adjacency[node]:
            if position == via:
                continue
            if neighbour not in discovery:
                walk(neighbour, position)
                low[node] = min(low[node], low[neighbour])
                if low[neighbour] <= discovery[node]:
                    in_ring.add(position)
            else:
                low[node] = min(low[node], discovery[neighbour])
                in_ring.add(position)

    for atom in atoms:
        if atom["idx"] not in discovery:
            walk(atom["idx"], -1)
    return in_ring


MAX_RING_SIZE = 8
AROMATIC_ELEMENTS = ("C", "N", "O", "S", "P")
AROMATICITY_METHOD = "huckel-4n2-v1"


def small_rings(atoms, bonds, max_size=MAX_RING_SIZE):
    """Return every simple cycle of at most ``max_size`` atoms.

    Rings are walked only over ring bonds and each is reported once, as the
    frozenset of its bond positions, starting from its lowest atom index.

    :rtype: list[frozenset[int]]
    """
    in_ring = ring_bonds(atoms, bonds)
    adjacency = {atom["idx"]: [] for atom in atoms}
    for position in in_ring:
        bond = bonds[position]
        adjacency[bond["atom_a"]].append((bond["atom_b"], position))
        adjacency[bond["atom_b"]].append((bond["atom_a"], position))
    found = set()

    def walk(start, node, path_atoms, path_bonds):
        for neighbour, position in adjacency[node]:
            if (
                neighbour == start
                and len(path_bonds) >= 2
                and position not in path_bonds
            ):
                found.add(frozenset(path_bonds + [position]))
            elif (
                neighbour > start
                and neighbour not in path_atoms
                and len(path_atoms) < max_size
            ):
                walk(
                    start, neighbour, path_atoms | {neighbour}, path_bonds + [position]
                )

    for start in sorted(adjacency):
        walk(start, start, {start}, [])
    return sorted(found, key=sorted)


def _pi_electrons(atom, links, in_ring, by_idx):
    """Return what ``atom`` gives a ring's π system, or ``None`` if it breaks it.

    :param list links: ``(neighbour idx, order, bond position)`` of the atom
    """
    element = atom["element"]
    charge = atom.get("formal_charge") or 0
    if element not in AROMATIC_ELEMENTS or any(order == 3 for _n, order, _p in links):
        return None
    doubles = [(n, p) for n, order, p in links if order == 2]
    if len(doubles) > 1:
        return None
    if doubles:
        neighbour, position = doubles[0]
        if position in in_ring:
            return 1
        # An exocyclic C=O, C=N or C=S pulls its electron out of the ring, as in
        # 2-pyridone; an exocyclic C=C leaves the ring non-aromatic, as in fulvene.
        return 0 if by_idx[neighbour]["element"] in ("N", "O", "S") else None
    if element == "C":
        return {1: 0, -1: 2}.get(charge)
    used = sum(order for _n, order, _p in links)
    count, over = implicit_hydrogens(element, charge, used)
    if over or lone_pairs(element, charge, used, count) == 0:
        return None
    return 2


def aromaticity(atoms, bonds):
    """Perceive aromatic rings by Hückel's 4n+2 rule.

    Each ring of up to eight atoms is tested alone, and two fused rings that are
    not aromatic alone are tested as one system, which is what azulene needs.
    Bond orders are left as drawn: aromaticity is reported beside them.

    :return: ``atoms`` (aromatic atom indices), ``bonds`` (aromatic bond
        positions), ``rings`` (number of small rings that are aromatic) and
        ``donors`` (aromatic atoms whose lone pair is part of the π system)
    :rtype: dict
    """
    by_idx = {atom["idx"]: atom for atom in atoms}
    in_ring = ring_bonds(atoms, bonds)
    links = {atom["idx"]: [] for atom in atoms}
    for position, bond in enumerate(bonds):
        links[bond["atom_a"]].append((bond["atom_b"], bond["bond_order"], position))
        links[bond["atom_b"]].append((bond["atom_a"], bond["bond_order"], position))
    electrons = {
        idx: _pi_electrons(by_idx[idx], links[idx], in_ring, by_idx) for idx in by_idx
    }

    def ring_atoms(ring):
        return {bonds[p]["atom_a"] for p in ring} | {bonds[p]["atom_b"] for p in ring}

    def huckel(members):
        figures = [electrons[idx] for idx in members]
        if None in figures:
            return False
        return sum(figures) % 4 == 2

    rings = small_rings(atoms, bonds)
    aromatic = [ring for ring in rings if huckel(ring_atoms(ring))]
    rest = [ring for ring in rings if ring not in aromatic]
    for position, first in enumerate(rest):
        for second in rest[position + 1 :]:
            if first & second and huckel(ring_atoms(first) | ring_atoms(second)):
                aromatic += [ring for ring in (first, second) if ring not in aromatic]
    aromatic_bonds = set().union(*aromatic) if aromatic else set()
    aromatic_atoms = set().union(*map(ring_atoms, aromatic)) if aromatic else set()
    return {
        "atoms": aromatic_atoms,
        "bonds": aromatic_bonds,
        "rings": len(aromatic),
        "donors": {idx for idx in aromatic_atoms if electrons[idx] == 2},
    }


def kekulize(atoms, bonds):
    """Turn bonds a molblock marks aromatic (type 4) into alternating orders.

    Every aromatic carbon needs one double bond; a nitrogen, phosphorus, oxygen
    or sulphur takes one only if the pattern needs it, which is how pyrrole's NH
    and pyridine's N are told apart without explicit hydrogens. Bonds are updated
    in place.

    :raises ValueError: when no alternation fits, i.e. the ring is not aromatic
        as written
    """
    marked = [position for position, bond in enumerate(bonds) if bond.get("aromatic")]
    if not marked:
        return
    by_idx = {atom["idx"]: atom for atom in atoms}
    partners = {}
    for position in marked:
        bond = bonds[position]
        bond["bond_order"] = 1
        partners.setdefault(bond["atom_a"], []).append((bond["atom_b"], position))
        partners.setdefault(bond["atom_b"], []).append((bond["atom_a"], position))
    has_double = {
        idx
        for position, bond in enumerate(bonds)
        if position not in marked and bond["bond_order"] == 2
        for idx in (bond["atom_a"], bond["atom_b"])
    }
    # A carbon with a formal charge or an exocyclic double bond already has
    # what it needs, as in the tropylium cation or 2-pyridone.
    needy = sorted(
        idx
        for idx in partners
        if by_idx[idx]["element"] == "C"
        and not by_idx[idx].get("formal_charge")
        and idx not in has_double
    )
    used = {atom["idx"]: 0 for atom in atoms}
    for bond in bonds:
        used[bond["atom_a"]] += bond["bond_order"]
        used[bond["atom_b"]] += bond["bond_order"]

    def can_take_double(idx):
        atom = by_idx[idx]
        if idx in has_double:
            return False
        if atom["element"] == "C":
            return not atom.get("formal_charge")
        # A heteroatom takes the double bond only within its lowest valence, so
        # thiophene's sulphur stays divalent instead of becoming S=C.
        options = effective_valences(atom["element"], atom.get("formal_charge") or 0)
        return bool(options) and used[idx] + 1 <= min(options)

    for links in partners.values():
        # carbons first, so a heteroatom is only reached for when a carbon is not
        links.sort(key=lambda link: (by_idx[link[0]]["element"] != "C", link[0]))
    matched = {}

    def assign(queue):
        if not queue:
            return True
        idx, rest = queue[0], queue[1:]
        if idx in matched:
            return assign(rest)
        for neighbour, position in partners[idx]:
            if neighbour in matched or not can_take_double(neighbour):
                continue
            matched[idx] = matched[neighbour] = position
            if assign(rest):
                return True
            del matched[idx], matched[neighbour]
        return False

    if not assign(needy):
        raise ValueError(
            "The aromatic bonds cannot be written as alternating single and double bonds."
        )
    for position in set(matched.values()):
        bonds[position]["bond_order"] = 2


def rotatable_bonds(atoms, bonds):
    """Count single acyclic bonds between two substituted heavy atoms.

    Amide C-N bonds are excluded. Other definitions give another number, which
    is why the method is recorded next to the value.

    :rtype: int
    """
    by_idx = {atom["idx"]: atom for atom in atoms}
    adjacency = _neighbours(atoms, bonds)
    in_ring = ring_bonds(atoms, bonds)

    def heavy_degree(idx):
        return sum(1 for n, _o in adjacency[idx] if by_idx[n]["element"] != "H")

    def is_amide(first, second):
        return (
            by_idx[first]["element"] == "N"
            and by_idx[second]["element"] == "C"
            and any(
                order == 2 and by_idx[n]["element"] == "O"
                for n, order in adjacency[second]
            )
        )

    count = 0
    for position, bond in enumerate(bonds):
        a, b = bond["atom_a"], bond["atom_b"]
        if bond["bond_order"] != 1 or position in in_ring:
            continue
        if by_idx[a]["element"] == "H" or by_idx[b]["element"] == "H":
            continue
        if heavy_degree(a) < 2 or heavy_degree(b) < 2:
            continue
        if is_amide(a, b) or is_amide(b, a):
            continue
        count += 1
    return count


def hill_formula(counts):
    """Render element counts in Hill notation: carbon, hydrogen, then alphabetical.

    :param dict counts: element symbol -> number of atoms
    :rtype: str
    """
    parts = []
    for symbol in ["C", "H"] + sorted(set(counts) - {"C", "H"}):
        total = counts.get(symbol, 0)
        if total:
            parts.append(symbol + (str(total) if total > 1 else ""))
    return "".join(parts)


# Valence electrons of the neutral atom, for the lone-pair count
VALENCE_ELECTRONS = {
    "H": 1,
    "C": 4,
    "N": 5,
    "P": 5,
    "O": 6,
    "S": 6,
    "F": 7,
    "Cl": 7,
    "Br": 7,
    "I": 7,
}

# Gasteiger-Marsili PEOE parameters (a, b, c) of χ = a + b·q + c·q².
# H, C, N, O, F, S, Cl, Br and I are the original 1980 table; the phosphorus row
# is a commonly cited extension and is flagged as such wherever it is used.
PEOE = {
    ("H", None): (7.17, 6.24, -0.56),
    ("C", "sp3"): (7.98, 9.18, 1.88),
    ("C", "sp2"): (8.79, 9.32, 1.51),
    ("C", "sp"): (10.39, 9.45, 0.73),
    ("N", "sp3"): (11.54, 10.82, 1.36),
    ("N", "sp2"): (12.87, 11.15, 0.85),
    ("N", "sp"): (15.68, 11.70, -0.27),
    ("O", "sp3"): (14.18, 12.92, 1.39),
    ("O", "sp2"): (17.07, 13.79, 0.47),
    ("F", None): (14.66, 13.85, 2.31),
    ("S", None): (10.14, 9.13, 1.38),
    ("P", None): (8.90, 8.24, 0.96),
    ("Cl", None): (11.00, 9.69, 1.35),
    ("Br", None): (10.08, 8.47, 1.16),
    ("I", None): (9.90, 7.96, 0.96),
}
# Electronegativity of the hydrogen cation, which the scheme fixes by hand
H_CATION = 20.02
HYBRIDISATION_ELEMENTS = ("C", "N", "O")
PEOE_METHOD = "gasteiger-peoe-v1"


def hybridisation(element, orders, aromatic=False):
    """Classify an atom from the bond orders around it.

    A triple bond or two doubles read as sp, one double or a place in an aromatic
    ring as sp², anything else as sp³. Without the aromatic flag pyrrole's NH and
    furan's O would read as sp³, which is not how their lone pair behaves.

    :param str element: element symbol
    :param list[int] orders: orders of the atom's explicit bonds
    :param bool aromatic: whether the atom sits in an aromatic ring
    :rtype: str
    """
    if element not in HYBRIDISATION_ELEMENTS:
        return "sp3"
    if 3 in orders or orders.count(2) >= 2:
        return "sp"
    if 2 in orders or aromatic:
        return "sp2"
    return "sp3"


def lone_pairs(element, charge, used, implicit_h=0):
    """Count the non-bonding electron pairs left on an atom.

    :param str element: element symbol
    :param int charge: formal charge
    :param int used: sum of the orders of the atom's explicit bonds
    :param int implicit_h: hydrogens completing the valence
    :rtype: int
    """
    electrons = VALENCE_ELECTRONS.get(element, 4) - charge - used - implicit_h
    return max(0, electrons // 2)


def hbond_profile(atoms, bonds):
    """Count hydrogen-bond donors and acceptors on nitrogen and oxygen.

    A donor is an N or O carrying at least one hydrogen; an acceptor is an N or O
    with a lone pair that is not part of an aromatic π system, so pyrrole's NH
    donates but does not accept while furan's O keeps its second pair. Lipinski's
    cruder count — every N and O — gives a different number, so the definition
    travels with the value.

    :rtype: tuple[int, int]
    """
    adjacency = _neighbours(atoms, bonds)
    by_idx = {atom["idx"]: atom for atom in atoms}
    in_pi = aromaticity(atoms, bonds)["donors"]
    donors = acceptors = 0
    for atom in atoms:
        if atom["element"] not in ("N", "O"):
            continue
        charge = atom.get("formal_charge") or 0
        used = sum(order for _n, order in adjacency[atom["idx"]])
        count, over = implicit_hydrogens(atom["element"], charge, used)
        if over:
            continue
        explicit_h = sum(
            1 for n, _o in adjacency[atom["idx"]] if by_idx[n]["element"] == "H"
        )
        if count + explicit_h:
            donors += 1
        pairs = lone_pairs(atom["element"], charge, used, count)
        if pairs - (atom["idx"] in in_pi):
            acceptors += 1
    return donors, acceptors


def gasteiger_charges(atoms, bonds, iterations=6):
    """Partial charges by partial equalisation of orbital electronegativity.

    This is the empirical scheme docking engines feed on, not a quantum
    calculation: there is no wavefunction here and no electronic energy. The
    charges are computed on the graph with its hydrogens made explicit, so an
    atom's own charge excludes the hydrogens hanging off it.

    :param list[dict] atoms: atoms with ``idx``, ``element``, ``formal_charge``
    :param list[dict] bonds: bonds with ``atom_a``, ``atom_b``, ``bond_order``
    :param int iterations: damped cycles; the scheme's own recipe uses six
    :return: ``{"atoms": {idx: charge}, "hydrogens": {idx: charge}, "total": float}``
        or ``None`` when an element has no parameters, because a missing row is
        not a zero
    :rtype: dict | None
    """
    adjacency = _neighbours(atoms, bonds)
    aromatic = aromaticity(atoms, bonds)["atoms"]
    nodes = []  # (element, hybridisation, charge, parent idx or None)
    index_of = {}
    for atom in atoms:
        element = atom["element"]
        charge = atom.get("formal_charge") or 0
        used = sum(order for _n, order in adjacency[atom["idx"]])
        orders = [order for _n, order in adjacency[atom["idx"]]]
        count, over = implicit_hydrogens(element, charge, used)
        kind = hybridisation(element, orders, atom["idx"] in aromatic)
        if over or ((element, None) not in PEOE and (element, kind) not in PEOE):
            return None
        index_of[atom["idx"]] = len(nodes)
        nodes.append([element, kind, float(charge), None])
        nodes.extend(["H", None, 0.0, atom["idx"]] for _ in range(count))

    links = [(index_of[bond["atom_a"]], index_of[bond["atom_b"]]) for bond in bonds]
    for position, node in enumerate(nodes):
        if node[3] is not None:
            links.append((index_of[node[3]], position))

    def parameters(node):
        element = node[0]
        return PEOE.get((element, node[1])) or PEOE[(element, None)]

    def cation_electronegativity(node):
        if node[0] == "H":
            return H_CATION
        a, b, c = parameters(node)
        return a + b + c

    charges = [node[2] for node in nodes]
    for cycle in range(1, iterations + 1):
        electronegativity = []
        for node, charge in zip(nodes, charges, strict=True):
            a, b, c = parameters(node)
            electronegativity.append(a + b * charge + c * charge * charge)
        transfer = [0.0] * len(nodes)
        damping = 0.5**cycle
        for first, second in links:
            if electronegativity[first] == electronegativity[second]:
                continue
            # Charge flows from the less to the more electronegative atom, scaled
            # by the donor's cation electronegativity.
            if electronegativity[first] > electronegativity[second]:
                donor, acceptor = second, first
            else:
                donor, acceptor = first, second
            flow = (
                (electronegativity[acceptor] - electronegativity[donor])
                / cation_electronegativity(nodes[donor])
                * damping
            )
            transfer[donor] += flow
            transfer[acceptor] -= flow
        charges = [
            charge + move for charge, move in zip(charges, transfer, strict=True)
        ]

    own, hydrogens = {}, {}
    for atom in atoms:
        own[atom["idx"]] = round(charges[index_of[atom["idx"]]], 4)
        hydrogens[atom["idx"]] = 0.0
    for position, node in enumerate(nodes):
        if node[3] is not None:
            hydrogens[node[3]] = round(hydrogens[node[3]] + charges[position], 4)
    return {"atoms": own, "hydrogens": hydrogens, "total": round(sum(charges), 4)}


def analyse(atoms, bonds):
    """Derive every published figure from a connection table.

    :param list[dict] atoms: atoms with ``idx``, ``element`` and ``formal_charge``
    :param list[dict] bonds: bonds with ``atom_a``, ``atom_b`` and ``bond_order``
    :return: formula, masses, charge, ring, aromatic-ring and π counts, rotatable
        bonds, and the atoms whose valence is exceeded — for which the masses are
        ``None`` rather than a number the table cannot support
    :rtype: dict
    """
    adjacency = _neighbours(atoms, bonds)
    counts, weight, monoisotopic, charge, exceeded = {}, 0.0, 0.0, 0, []
    implicit_total = 0

    for atom in atoms:
        element = atom["element"]
        if element not in WEIGHTS:
            exceeded.append({"idx": atom["idx"], "element": element, "used": 0})
            continue
        counts[element] = counts.get(element, 0) + 1
        weight += WEIGHTS[element]
        monoisotopic += MONOISOTOPIC[element]
        charge += atom.get("formal_charge") or 0
        used = sum(order for _n, order in adjacency[atom["idx"]])
        count, over = implicit_hydrogens(element, atom.get("formal_charge") or 0, used)
        if over:
            exceeded.append({"idx": atom["idx"], "element": element, "used": used})
        elif count:
            implicit_total += count
            counts["H"] = counts.get("H", 0) + count
            weight += WEIGHTS["H"] * count
            monoisotopic += MONOISOTOPIC["H"] * count

    hbd, hba = hbond_profile(atoms, bonds)
    rings = (
        max(0, len(bonds) - len(atoms) + _components(atoms, adjacency)) if atoms else 0
    )
    pi_bonds = sum(bond["bond_order"] - 1 for bond in bonds)
    return {
        "formula": hill_formula(counts),
        "counts": counts,
        "weight": None if exceeded else round(weight, 4),
        "monoisotopic": None if exceeded else round(monoisotopic, 5),
        "charge": charge,
        "implicit_h": implicit_total,
        "rings": rings,
        "aromatic_rings": aromaticity(atoms, bonds)["rings"] if bonds else 0,
        "pi_bonds": pi_bonds,
        "unsaturation": rings + pi_bonds,
        "heavy_atoms": sum(1 for atom in atoms if atom["element"] != "H"),
        "bond_count": len(bonds),
        "rotatable_bonds": rotatable_bonds(atoms, bonds) if bonds else 0,
        "hbd": hbd,
        "hba": hba,
        "exceeded": exceeded,
    }
