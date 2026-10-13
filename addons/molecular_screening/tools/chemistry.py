
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
    labels = {atom["idx"]: (atom["element"], atom["formal_charge"]) for atom in atoms}
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
    if Chem is not None:
        mol = None
        if molblock:
            mol = Chem.MolFromMolBlock(molblock, sanitize=True, removeHs=False)
        if mol is None and smiles:
            mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            inchikey = Chem.MolToInchiKey(mol) or None
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
    digest = hashlib.sha1(smiles.encode()).hexdigest()
    return {
        "inchikey": None,
        "smiles_canon": smiles,
        "identity_key": f"SM1-{digest[:23].upper()}",
        "method": SMILES_HASH_METHOD,
    }
