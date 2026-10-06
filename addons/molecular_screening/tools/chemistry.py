"""Chemical identity helpers.

RDKit gives a real InChIKey; where it is not installed the module still has to
deduplicate compounds, so it falls back to a structural hash of the connection
table. Both carry their provenance in ``method`` so no number ever looks more
authoritative than it is.
"""

import hashlib

try:
    from rdkit import Chem
    from rdkit import __version__ as RDKIT_VERSION
except ImportError:
    Chem = None
    RDKIT_VERSION = None

STRUCTURAL_HASH_METHOD = "structural-hash-v1"
SMILES_HASH_METHOD = "smiles-hash-v1"


def _structural_hash(atoms, bonds):
    """Hash the connectivity of a structure, ignoring coordinates and order.

    :param list[dict] atoms: atoms as returned by ``parse_molblock``
    :param list[dict] bonds: bonds as returned by ``parse_molblock``
    :rtype: str
    """
    labels = {atom["idx"]: (atom["element"], atom["formal_charge"]) for atom in atoms}
    # Sorting by chemical label instead of by index keeps the hash stable when
    # the same molecule is written with its atoms in another order.
    atom_part = sorted(f"{element}{charge:+d}" for element, charge in labels.values())
    bond_part = sorted(
        "{}-{}:{}".format(
            *sorted(
                (
                    "{}{:+d}".format(*labels[bond["atom_a"]]),
                    "{}{:+d}".format(*labels[bond["atom_b"]]),
                )
            ),
            bond["bond_order"],
        )
        for bond in bonds
    )
    digest = hashlib.sha1("|".join(atom_part + ["#"] + bond_part).encode()).hexdigest()
    return f"SH1-{digest[:23].upper()}"


def compute_identity(molblock=None, smiles=None, atoms=None, bonds=None):
    """Derive the identity of a compound from whatever representation is at hand.

    :param str molblock: V2000 connection table, preferred input
    :param str smiles: SMILES string, used when no molblock is available
    :param list[dict] atoms: parsed atoms, to avoid parsing the molblock twice
    :param list[dict] bonds: parsed bonds
    :return: ``inchikey``, ``smiles_canon``, ``identity_key`` and ``method``
    :rtype: dict
    """
    if Chem is not None:
        mol = None
        if molblock:
            mol = Chem.MolFromMolBlock(molblock, sanitize=True, removeHs=False)
        if mol is None and smiles:
            mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            inchikey = Chem.MolToInchiKey(mol) or None
            # The first block of an InChIKey is the skeleton: it ignores the
            # stereo layer, so one molecule drawn with and without its double
            # bond geometry lands on a single compound, the way the structural
            # hash does. The full key stays on the record for exactness.
            identity_key = inchikey[:14] if inchikey else None
            return {
                "inchikey": inchikey,
                "smiles_canon": Chem.MolToSmiles(mol),
                "identity_key": identity_key
                or _structural_hash(atoms or [], bonds or []),
                "method": f"rdkit-{RDKIT_VERSION}-skeleton"
                if identity_key
                else STRUCTURAL_HASH_METHOD,
            }
    if atoms:
        return {
            "inchikey": None,
            "smiles_canon": smiles or None,
            "identity_key": _structural_hash(atoms, bonds or []),
            "method": STRUCTURAL_HASH_METHOD,
        }
    if not smiles:
        raise ValueError("A molblock or a SMILES string is required.")
    # No connection table and no toolkit: the SMILES text is all there is, so
    # two spellings of one molecule will not collapse into a single compound.
    digest = hashlib.sha1(smiles.encode()).hexdigest()
    return {
        "inchikey": None,
        "smiles_canon": smiles,
        "identity_key": f"SM1-{digest[:23].upper()}",
        "method": SMILES_HASH_METHOD,
    }
