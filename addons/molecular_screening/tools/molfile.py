from .valence import kekulize


def parse_molblock(molblock):
    lines = molblock.replace("\r\n", "\n").split("\n")
    if len(lines) < 4 or "V2000" not in lines[3]:
        raise ValueError("Only V2000 molblocks are supported.")
    try:
        atom_count, bond_count = int(lines[3][0:3]), int(lines[3][3:6])
        atoms = []
        for idx, line in enumerate(lines[4 : 4 + atom_count], start=1):
            atoms.append(
                {
                    "idx": idx,
                    "x": float(line[0:10]),
                    "y": float(line[10:20]),
                    "z": float(line[20:30]),
                    "element": line[31:34].strip(),
                    "formal_charge": 0,
                }
            )
        bonds = []
        for line in lines[4 + atom_count : 4 + atom_count + bond_count]:
            a, b = int(line[0:3]), int(line[3:6])
            order = int(line[6:9])
            bonds.append(
                {
                    "atom_a": min(a, b),
                    "atom_b": max(a, b),
                    "bond_order": 1 if order == 4 else order,
                    "aromatic": order == 4,
                    "stereo": int(line[9:12] or 0),
                }
            )
        for line in lines[4 + atom_count + bond_count :]:
            if line.startswith("M  CHG"):
                fields = line.split()
                for atom_idx, charge in zip(fields[3::2], fields[4::2], strict=True):
                    atoms[int(atom_idx) - 1]["formal_charge"] = int(charge)
            elif line.startswith("M  END"):
                break
    except (ValueError, IndexError) as err:
        raise ValueError(f"Malformed V2000 molblock: {err}") from None
    if len(atoms) != atom_count or len(bonds) != bond_count:
        raise ValueError("The molblock declares more records than it carries.")
    kekulize(atoms, bonds)
    return atoms, bonds


def build_molblock(atoms, bonds, title="molecular-screening", dimension="2D"):
    lines = [title, f"  molecular_screening      {dimension}", ""]
    lines.append(f"{len(atoms):>3}{len(bonds):>3}  0  0  0  0  0  0  0  0999 V2000")
    for atom in atoms:
        coordinates = "".join(
            f"{float(atom.get(axis) or 0.0):>10.4f}" for axis in ("x", "y", "z")
        )
        lines.append(
            f"{coordinates} {atom['element']:<3} 0  0  0  0  0  0  0  0  0  0  0  0"
        )
    lines.extend(
        f"{bond['atom_a']:>3}{bond['atom_b']:>3}{bond['bond_order']:>3}"
        f"{bond.get('stereo') or 0:>3}"
        for bond in bonds
    )
    charged = [
        (index, atom["formal_charge"])
        for index, atom in enumerate(atoms, start=1)
        if atom.get("formal_charge")
    ]
    for start in range(0, len(charged), 8):
        chunk = charged[start : start + 8]
        entries = "".join(f"{idx:>4}{charge:>4}" for idx, charge in chunk)
        lines.append(f"M  CHG{len(chunk):>3}{entries}")
    lines.append("M  END")
    return "\n".join(lines) + "\n"
