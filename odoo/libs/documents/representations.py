from __future__ import annotations

__all__ = [
    "ANY",
    "BARCODES",
    "CHEAP",
    "CHILDREN",
    "CUES",
    "DATA",
    "FREE",
    "GENERATIVE",
    "IMAGES",
    "METERED",
    "REPRESENTATIONS",
    "ROWS",
    "SHEETS",
    "TEXT",
    "TREE",
]

ROWS = "rows"
TEXT = "text"
TREE = "tree"
DATA = "data"
IMAGES = "images"
BARCODES = "barcodes"
CHILDREN = "children"
CUES = "cues"
SHEETS = "sheets"

REPRESENTATIONS = (ROWS, TEXT, TREE, DATA, IMAGES, BARCODES, CHILDREN, CUES, SHEETS)

ANY = "*"

FREE = 0
CHEAP = 10
METERED = 20
GENERATIVE = 30
