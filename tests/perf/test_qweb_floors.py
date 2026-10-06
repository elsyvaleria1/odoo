from __future__ import annotations

import time

from lxml import etree

ROWS = 10_000

ROW = (
    '<t t-name="perf.row">'
    "<tr t-att-data-id=\"row['id']\" t-attf-class=\"r #{'odd' if row_odd else 'even'}\">"
    "<td t-out=\"row['name']\"/>"
    '<td><t t-if="row[\'active\']">yes</t><t t-else="">no</t></td>'
    "<td t-att-title=\"row['note']\" t-out=\"row['price']\"/>"
    "</tr></t>"
)
TEMPLATES = {
    "perf.row": ROW,
    "perf.call_per_row": (
        '<t t-name="perf.call_per_row"><table>'
        '<t t-foreach="rows" t-as="row"><t t-call="perf.row"/></t>'
        "</table></t>"
    ),
    "perf.flat": (
        '<t t-name="perf.flat"><table><t t-foreach="rows" t-as="row">'
        + ROW.removeprefix('<t t-name="perf.row">').removesuffix("</t>")
        + "</t></table></t>"
    ),
}


def _rows():
    return [
        {
            "id": i,
            "name": f"Item {i} <b>&amp;</b> 'x'" if i % 7 == 0 else f"Item {i}",
            "price": round((i * 1.37) % 1000, 2),
            "active": i % 3 != 0,
            "note": f'note "{i}" & co' if i % 2 else False,
        }
        for i in range(ROWS)
    ]


def _render_ms(name, rows, repeat=7):
    from odoo.addons.base.models.ir_qweb import render

    def load(ref):
        return etree.fromstring(TEMPLATES[ref]), ref

    render(name, {"rows": rows}, load)
    readings = []
    for _ in range(repeat):
        start = time.process_time()
        render(name, {"rows": rows}, load)
        readings.append((time.process_time() - start) * 1000)
    return round(min(readings), 1)


def test_qweb_render_floor(check):
    rows = _rows()
    check(
        "qweb_render_10k_rows",
        {
            "flat_ms": _render_ms("perf.flat", rows),
            "call_per_row_ms": _render_ms("perf.call_per_row", rows),
        },
    )
