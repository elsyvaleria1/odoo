BENZENE = """benzene
  molecular_screening      2D

  6  6  0  0  0  0  0  0  0  0999 V2000
    0.0000    1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  1  6  1  0
M  END
"""

ACETONITRILE = """acetonitrile
  molecular_screening      2D

  3  2  0  0  0  0  0  0  0  0999 V2000
   -1.4000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4000    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  3  0
M  END
"""

NITROMETHANE_ANION = """nitromethane-anion
  molecular_screening      2D

  4  3  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4000    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
    2.1000    1.2000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    2.1000   -1.2000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  2  1  1  0
  2  3  2  0
  4  2  1  0
M  CHG  2   2   1   4  -1
M  END
"""

OVERLOADED = """overloaded
  molecular_screening      2D

  6  5  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4000    0.0000    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0
   -1.4000    0.0000    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.4000    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.4000    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    1.0000    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  1  3  1  0
  1  4  1  0
  1  5  1  0
  1  6  1  0
M  END
"""

PYRROLE = """pyrrole
  molecular_screening      2D

  5  5  0  0  0  0  0  0  0  0999 V2000
    0.0000    1.4000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
    1.3315    0.4326    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.8229   -1.1326    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.8229   -1.1326    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.3315    0.4326    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  2  0
  3  4  1  0
  4  5  2  0
  5  1  1  0
M  END
"""

PYRIDINE_AROMATIC = """pyridine-aromatic
  molecular_screening      2D

  6  6  0  0  0  0  0  0  0  0999 V2000
    0.0000    1.4000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  4  0
  2  3  4  0
  3  4  4  0
  4  5  4  0
  5  6  4  0
  6  1  4  0
M  END
"""

EXPECTED = {
    "benzene": {
        "formula": "C6H6",
        "weight": 78.114,
        "monoisotopic": 78.04695,
        "charge": 0,
        "rings": 1,
        "unsaturation": 4,
        "rotatable_bonds": 0,
        "heavy_atoms": 6,
        "aromatic_rings": 1,
    },
    "acetonitrile": {
        "formula": "C2H3N",
        "weight": 41.053,
        "monoisotopic": 41.02655,
        "charge": 0,
        "rings": 0,
        "unsaturation": 2,
        "rotatable_bonds": 0,
        "heavy_atoms": 3,
        "aromatic_rings": 0,
    },
    "nitromethane_anion": {
        "formula": "CH3NO2",
        "weight": 61.04,
        "monoisotopic": 61.01638,
        "charge": 0,
        "rings": 0,
        "unsaturation": 1,
        "rotatable_bonds": 0,
        "heavy_atoms": 4,
        "aromatic_rings": 0,
    },
    "pyrrole": {
        "formula": "C4H5N",
        "weight": 67.091,
        "monoisotopic": 67.04220,
        "charge": 0,
        "rings": 1,
        "unsaturation": 3,
        "rotatable_bonds": 0,
        "heavy_atoms": 5,
        "aromatic_rings": 1,
    },
    "pyridine_aromatic": {
        "formula": "C5H5N",
        "weight": 79.102,
        "monoisotopic": 79.04220,
        "charge": 0,
        "rings": 1,
        "unsaturation": 4,
        "rotatable_bonds": 0,
        "heavy_atoms": 6,
        "aromatic_rings": 1,
    },
}
