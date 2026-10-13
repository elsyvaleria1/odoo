import logging
from pathlib import Path
from typing import Any, Literal

from odoo import api, fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.modules.module import get_manifest, get_module_path
from odoo.tools import frozendict
from odoo.tools.convert import (
    convert_csv_import,
    convert_xml_import,
    data_file_records,
)

from .ir_access import NON_STANDARD_MODULES
from .ir_access_convert import shipped_access_records
from .ir_access_log import kept_on_uninstall

_logger = logging.getLogger(__name__)

DRIFT_LOG_EVENTS = [("access_drift", "Access row drifted from its file")]

type _DriftIdentity = tuple[str | Literal[False], int | Literal[False], str]


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"

    event = fields.Selection(
        selection_add=DRIFT_LOG_EVENTS,
        ondelete=kept_on_uninstall(DRIFT_LOG_EVENTS),
    )


class _Replayed(Exception):
    pass


class IrAccessDrift(models.Model):
    _name = "ir.access.drift"
    _description = "Access Drift"
    _order = "state, xmlid, id"
    _rec_name = "xmlid"
    _allow_sudo_commands = False
    _access_anchors = frozendict({"company": ""})

    access_id = fields.Many2one(
        comodel_name="ir.access",
        index=True,
        readonly=True,
        ondelete="cascade",
    )
    xmlid = fields.Char(
        string="External ID",
        index=True,
        readonly=True,
    )
    module = fields.Char(readonly=True)
    state = fields.Selection(
        selection=[
            ("differs", "Differs from its file"),
            ("missing", "Shipped, not in the database"),
            ("orphan", "Shipped by no installed module"),
            ("custom", "Written without a module"),
            ("unreadable", "Its module's files do not load"),
        ],
        readonly=True,
        required=True,
    )
    changed = fields.Char(
        string="Fields",
        readonly=True,
        help="The fields the row holds otherwise than its file ships them.",
    )
    detail = fields.Text(
        readonly=True,
        help="Each field as the database holds it, then as the file ships it.",
    )
    writer_id = fields.Many2one(
        comodel_name="res.users",
        string="Last Written By",
        readonly=True,
        ondelete="set null",
    )
    first_seen = fields.Datetime(
        readonly=True,
        required=True,
    )

    @api.model
    def _cron_scan(self) -> None:
        self._scan()

    @api.model
    def _scan(self) -> dict[str, int]:
        found = self._get_findings_by_identity()
        standing = {
            (drift.xmlid, drift.access_id.id, drift.state): drift
            for drift in self.search([])
        }
        new: list[dict[str, Any]] = []
        for key, values in found.items():
            if drift := standing.pop(key, None):
                drift.write(
                    {
                        name: values.get(name)
                        for name in ("changed", "detail", "writer_id")
                    }
                )
            else:
                new.append({**values, "first_seen": self.env.cr.now()})
        self.browse().union(*standing.values()).unlink()
        created = self.create(new)
        created._log()
        counts: dict[str, int] = {}
        for values in found.values():
            counts[values["state"]] = counts.get(values["state"], 0) + 1
        _logger.info("ir.access drift: %s (%s new)", counts or "none", len(created))
        return counts

    def _log(self) -> None:
        self.env["ir.access.log"]._record(
            [
                {
                    "event": "access_drift",
                    "model_name": "ir.access",
                    "res_ids": str(drift.access_id.id) if drift.access_id else False,
                    "cause": drift.state,
                    "cause_model": self._name,
                    "cause_res_id": drift.id,
                    "reason": f"{drift.xmlid or drift.access_id.display_name}: "
                    f"{drift.changed or dict(self._fields['state'].selection)[drift.state]}"[
                        :255
                    ],
                }
                for drift in self
            ]
        )

    @api.model
    def _get_findings_by_identity(self) -> dict[_DriftIdentity, dict[str, Any]]:
        Access = self.env["ir.access"].with_context(active_test=False)
        names = [
            name
            for name, field in Access._fields.items()
            if field.store
            and name not in models.MAGIC_COLUMNS
            and field.type != "one2many"
        ]
        installed = self._installed_in_load_order()
        shipped: dict[str, bool] = {}
        for module in installed:
            for xmlid, _values, noupdate in shipped_access_records(module):
                shipped[xmlid] = shipped.get(xmlid, True) and noupdate

        before = {row["id"]: row for row in Access.search([]).read(names)}
        xmlids = self._xmlids()
        found: dict[_DriftIdentity, dict[str, Any]] = {}
        after: dict[int, dict[str, Any]] = {}
        replayed_xmlids: dict[int, str] = {}
        try:
            with self.env.cr.savepoint():
                for module in installed:
                    error, legacy = self._replay(module)
                    shipped.update(legacy)
                    if error:
                        found[(module, False, "unreadable")] = {
                            "xmlid": module,
                            "module": module,
                            "state": "unreadable",
                            "detail": error,
                        }
                self.env.flush_all()
                after = {row["id"]: row for row in Access.search([]).read(names)}
                replayed_xmlids = self._xmlids()
                raise _Replayed
        except _Replayed:
            pass
        finally:
            self.env.invalidate_all()
            self.env.registry.clear_cache("stable", "groups", "templates")

        for access_id, row in after.items():
            xmlid = replayed_xmlids.get(access_id) or False
            if access_id not in before:
                found[(xmlid, False, "missing")] = {
                    "xmlid": xmlid,
                    "module": xmlid and xmlid.split(".", 1)[0],
                    "state": "missing",
                    "detail": _render(names, {}, row),
                }
                continue
            changed = [
                name
                for name in names
                if _value(before[access_id][name]) != _value(row[name])
            ]
            if changed and not shipped.get(xmlid):
                found[(xmlid, access_id, "differs")] = {
                    "access_id": access_id,
                    "xmlid": xmlid,
                    "module": xmlid and xmlid.split(".", 1)[0],
                    "state": "differs",
                    "changed": ", ".join(changed),
                    "detail": _render(changed, before[access_id], row),
                }
        writers = self._writers(before)
        for access_id, row in before.items():
            if not row["active"]:
                continue
            xmlid = xmlids.get(access_id) or False
            module = xmlid and xmlid.split(".", 1)[0]
            if not xmlid or module in NON_STANDARD_MODULES:
                state = "custom"
            elif xmlid not in shipped:
                state = "orphan"
            else:
                continue
            found[(xmlid, access_id, state)] = {
                "access_id": access_id,
                "xmlid": xmlid,
                "module": module,
                "state": state,
                "writer_id": writers.get(access_id),
            }
        for (_xmlid, access_id, _state), values in found.items():
            if access_id:
                values.setdefault("writer_id", writers.get(access_id))
        return found

    @api.model
    def _replay(self, module: str) -> tuple[str | None, dict[str, bool]]:
        path = get_module_path(module, display_warning=False)
        if not path:
            return None, {}
        legacy: dict[str, bool] = {}
        try:
            with self.env.cr.savepoint():
                for name in get_manifest(module, path).get("data", ()):
                    file = Path(path, name)
                    if not file.is_file():
                        continue
                    if file.name == "ir.access.csv":
                        convert_csv_import(
                            self.env, module, name, file.read_bytes(), mode="init"
                        )
                    elif file.suffix == ".xml":
                        content = data_file_records(
                            file,
                            lambda record, noupdate: (
                                record.get("model") == "ir.access"
                                and bool(record.get("id"))
                                and not noupdate
                            ),
                        )
                        if content is not None:
                            convert_xml_import(self.env, module, content, mode="init")
                legacy = self.env["ir.access"]._load_legacy_access(module, "init")
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception as error:
            _logger.warning("ir.access drift: %s does not replay: %s", module, error)
            return f"{type(error).__name__}: {error}"[:2000], legacy
        return None, legacy

    @api.model
    def _installed_in_load_order(self) -> list[str]:
        self.env.cr.execute(
            """
            SELECT m.name, d.name
              FROM ir_module_module m
              LEFT JOIN ir_module_module_dependency d ON d.module_id = m.id
             WHERE m.state = 'installed'
            """
        )
        depends: dict[str, set[str]] = {}
        for name, dependency in self.env.cr.fetchall():
            depends.setdefault(name, set())
            if dependency:
                depends[name].add(dependency)
        ordered: list[str] = []
        placed: set[str] = set()

        def place(name: str, path: tuple[str, ...] = ()) -> None:
            if name in placed or name in path or name not in depends:
                return
            for dependency in sorted(depends[name]):
                place(dependency, (*path, name))
            placed.add(name)
            ordered.append(name)

        for name in sorted(depends):
            place(name)
        return ordered

    @api.model
    def _xmlids(self) -> dict[int, str]:
        self.env.cr.execute(
            "SELECT res_id, module || '.' || name FROM ir_model_data "
            "WHERE model = 'ir.access' ORDER BY id"
        )
        return dict(self.env.cr.fetchall())

    @api.model
    def _writers(self, rows: dict[int, dict[str, Any]]) -> dict[int, int]:
        self.env.cr.execute(
            "SELECT id, write_uid FROM ir_access WHERE id = ANY(%s)", [list(rows)]
        )
        return {access_id: uid for access_id, uid in self.env.cr.fetchall() if uid}


def _value(value: Any) -> Any:
    if isinstance(value, tuple):
        return value[0]
    if isinstance(value, list):
        return tuple(sorted(value))
    return value


def _render(names: list[str], held: dict[str, Any], shipped: dict[str, Any]) -> str:
    return "\n".join(
        f"{name}: {_value(held.get(name))!r} -> {_value(shipped.get(name))!r}"
        for name in names
        if _value(held.get(name)) != _value(shipped.get(name))
    )
