# Molecular Screening

Tracks a virtual screening campaign inside Odoo: the targets and their redocking
gate, the compound library with its roles, the geometries of each compound, and
the docking jobs that may run once a target has earned the right to be ranked.

It also carries its own sketch editor, so a molecule can be drawn, checked and
stored without leaving the database.

## What the module holds

| Model | What it is for |
|---|---|
| `molecular.screening.campaign` | One screening exercise, with its state and counts |
| `molecular.target` | A receptor, and the validation run that currently governs it |
| `molecular.validation.run` | One redocking attempt: box, engine, scoring, RMSD, poses |
| `molecular.compound` | Chemical identity: one row per molecule, whatever its geometry |
| `molecular.compound.role` | What a compound is *in a campaign*: reference, candidate, control |
| `molecular.compound.property` | A computed value **plus the method that produced it** |
| `molecular.structure` | One geometry: 2D drawing, 3D conformer or protonated form |
| `molecular.structure.atom` / `.bond` | The connection table, queryable in SQL, each atom with its hybridisation, lone pairs, implicit H and partial charge |
| `molecular.docking.job` | Per target: pending, running, done, error or **blocked** |
| `molecular.docking.result` | A scored pose, always attached to a job |

Three consequences worth stating, because they are the reason for the shape:

- **A failing target blocks only itself.** The gate lives on the job, so one
  target failing its redocking leaves the campaign's other targets free to run.
- **The same molecule under two names is one row.** Roles carry the difference,
  so a compound that is both reference and control is counted once.
- **A validation attempt is never overwritten.** The failed run and its retry
  sit side by side; `active_validation_id` says which one governs today.

## Access and company ownership

The chemical library (identities, classes, properties and geometries) is shared
across companies. A campaign and its targets, roles, validation attempts and
docking results belong to the campaign company. Screening users can read, create
and update in their company scope; managers can also delete whole records.
Atom and bond rows may be replaced by anyone who can edit their structure. Cross-company
records stay protected even when their compound is shared.

Existing campaigns acquire their responsible user’s company when upgrading
from 1.0.0, falling back to their creator’s company for unassigned campaigns.
Review that assignment before granting screening access.

## Getting molecules in

- **`tools/sdf_parser.py`** splits an SD file into records with their molblock
  and data tags; an importer for a given pipeline's tag names builds on it.
- **Draw a Molecule**: the sketch editor, also reachable from a compound's
  *Open in Editor*. Click to place atoms, click two atoms to bond, click a bond
  to cycle single → double → triple, drag to rearrange, and set formal charges.
  It relaxes a 3D geometry on demand and can keep it as a conformer.

The editor's live panel runs `static/src/molecule_editor/chemistry.js`; every
value that reaches the database is recomputed server side by
`tools/valence.py`. Both read the same fixtures in `tests/fixtures.py`, so the
two implementations cannot drift apart without a test going red.

## Asking questions of the library

- **By composition** — `element_symbols` holds the element list of each compound,
  so "everything carrying bromine" is a search and not a formula parse. The
  compound search also takes the formula directly, and ships a *Halogenated*
  filter and a *Charged* filter.
- **By role** — candidates, references and controls, per campaign.
- **By provenance** — the property list shows which method produced each value.

## Electronic structure, as far as is honest

The module computes what a connection table can support without a wavefunction:

- **Hybridisation** of every atom, read from its bond orders.
- **Lone pairs**, from valence electrons minus bonds, hydrogens and charge.
- **Hydrogen-bond donors and acceptors** — N and O carrying a hydrogen, and N
  and O keeping a lone pair.
- **Partial charges** by Gasteiger–Marsili PEOE, the empirical scheme AutoDock
  and smina feed on. Each atom stores its own charge and, separately, the charge
  of the hydrogens completing it, which is the number a docking engine merges in.

This is **not** quantum chemistry: there is no wavefunction, no orbital energy,
no HOMO–LUMO gap and no electronic energy. For those, the realistic next step on
a machine without a GPU is **xtb** (GFN2-xTB) run as an external job whose
results land in a table beside these, with its own method string. Nothing in the
module pretends to do it today.

## What is exact

- **Formula and counts** — read from the connection table you drew or imported.
- **Masses** — sums of IUPAC 2021 standard atomic weights and of the most
  abundant isotope's mass. The arithmetic is exact; the uncertainty is the table's.
- **Total charge** — the sum of the formal charges on the record.
- **Rings and unsaturation** — cyclomatic number (bonds − atoms + components)
  plus the π bonds. For a graph this is an identity, not an estimate.
- **Ring membership** — a bond is in a ring exactly when it is not a bridge.
- **Molfile** — V2000 with an `M  CHG` block, read by Avogadro and RDKit.

## What is approximate

- **Implicit hydrogens** — the element's typical valence adjusted by charge.
  When the valence is exceeded the count is *not* published: the field reads a
  dash, the mass is left unset, and a warning names the atom.
- **Rotatable bonds** — single, acyclic, two heavy neighbours at each end,
  amide C−N excluded. Another definition gives another number, which is why the
  method is stored next to the value.
- **Partial charges** — Gasteiger–Marsili is an empirical equalisation scheme
  fitted in 1980, not a calculation from first principles. Charge is conserved
  exactly; where it sits is an approximation. The parameters cover H, C, N, O,
  F, S, Cl, Br and I from the original table, plus a commonly cited phosphorus
  row. An element outside that set leaves `charge_method` empty and every charge
  at zero, so a missing parameter never passes for a computed zero.
- **Hydrogen bonding** — donors and acceptors follow the lone-pair definition
  above; Lipinski's cruder count of every N and O gives a different number.
- **3D geometry** — bond springs from covalent radii, angles from hybridisation
  (sp 180°, sp² 120°, sp³ 109.5°), repulsion between atoms three bonds apart or
  more, and a planarity term at sp² centres. Good for connectivity and rough
  shape.

## What is out of scope

- **Not docking quality.** The relaxed geometry replaces neither an ETKDG+MMFF
  conformer nor a docked pose, and must not feed a screening run.
- **No quantum chemistry.** No wavefunction, orbital energies or electronic
  energy. The partial charges above are empirical and say nothing about them.
- **No stereochemistry.** Chirality and E/Z are not perceived; molfile wedges
  are written as 0.
- **Aromaticity is Hückel's rule only.** Rings of up to eight atoms and fused
  pairs are tested for 4n+2 π electrons; bond orders stay in Kekulé form and
  `aromatic` is a flag on atoms and bonds.
- **InChIKey needs RDKit.** Where RDKit is installed, identity is the InChIKey's
  skeleton block; where it is not, a hash of the connection table. Both ignore
  stereochemistry on purpose, so the same molecule drawn either way is one row.

## Testing

```bash
odoo-bin -d <db> -u molecular_screening --test-enable --test-tags /molecular_screening
```

The suite covers the molfile parser, the valence table, the electronic figures
(charge conservation, benzene's equivalent carbons, the anion carrying its
charge), identity and deduplication, the SDF parser, the validation gate and
its blocking, and two browser tests that exercise the 3D viewer and the full
draw → relax → save flow.

Third-party: 3Dmol.js 2.4.2 (BSD-3), vendored in `static/lib/3dmol/`.
