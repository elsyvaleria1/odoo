import typing
from collections import defaultdict
from itertools import batched

from odoo.db.schema import column_exists
from odoo.libs.debug_log import DebugLog
from odoo.tools.cache import TransactionMemo

from ...fields.reference import REFERENCE_VERIFIED_CACHE_KEY, Reference
from ...primitives import MODULE_UNINSTALL_FLAG
from ...profiling import _OrmProfile
from ._crud_common import (
    _orm_crud,
    _unlink,
)
from ._model_stubs import _ModelStubs

_UNLINK_LOG_MAX_IDS = 1000

_debug = DebugLog(__name__)

if typing.TYPE_CHECKING:
    from ..._typing import BaseModel
    from ...fields import Field
    from ...fields.relational._base import _RelationalMulti


class UnlinkMixin(_ModelStubs):
    __slots__ = ()

    def unlink(self) -> typing.Literal[True]:
        if not self:
            return True

        TransactionMemo.discard_for_model(self.env, self._name)
        prof = _OrmProfile(_orm_crud)

        if self.env.transaction.observers:
            self.env.transaction.observe_operation(
                "unlink", self._name, len(self), frozenset()
            )

        self.check_access("unlink")
        prof.mark("acl")

        _debug.lifecycle(
            "unlink.records",
            model=self._name,
            records=len(self),
            uid=self.env.uid,
            uninstalling=bool(self.env.context.get(MODULE_UNINSTALL_FLAG)),
        )
        ondelete_run = 0  # debuglog
        for func in self._ondelete_methods:
            if func._ondelete or not self.env.context.get(MODULE_UNINSTALL_FLAG):
                ondelete_run += 1  # debuglog
                func(self)
        _debug.pipeline(
            "unlink.ondelete",
            model=self._name,
            records=len(self),
            methods=len(self._ondelete_methods),
            run=ondelete_run,
        )
        prof.mark("ondelete")

        self._unlink_inheritance_rows_cascaded()

        self._defer_dependent_recomputes()
        self._discard_pending_recomputes()
        self.env.flush_all()
        prof.mark("flush")

        cr = self.env.cr
        ir_model_data_unlink = self.env.registry.xmlids.records_of(self)
        ir_attachment_unlink = self.env.registry.file_store.of_records(self)

        with self.env.protecting(self._fields.values(), self):
            self._modified_before(self._fields)
            self._modified_many2many_corecords()

        self._discard_pending_recomputes()
        prof.mark("before")

        deleted_ids: list[int] = self.ids
        for sub_ids in batched(deleted_ids, cr.BATCH_SIZE, strict=False):
            self._unlink_process_batch(sub_ids)
        prof.mark("sql")

        if self.env.context.get(MODULE_UNINSTALL_FLAG):
            self.env.invalidate_all(flush=False)
            self.env.cr.cache.pop(REFERENCE_VERIFIED_CACHE_KEY, None)
        else:
            self._invalidate_after_unlink()

        _debug.pipeline(
            "unlink.cascade",
            model=self._name,
            records=len(deleted_ids),
            xmlids=len(ir_model_data_unlink),
            attachments=len(ir_attachment_unlink),
            uninstalling=bool(self.env.context.get(MODULE_UNINSTALL_FLAG)),
        )
        if ir_model_data_unlink:
            typing.cast("BaseModel", ir_model_data_unlink).unlink()
        if ir_attachment_unlink:
            typing.cast("BaseModel", ir_attachment_unlink).unlink()

        self._log_unlinked_ids(deleted_ids)

        prof.stop("invalidate")
        self._log_unlink_profile(prof, len(deleted_ids))

        return True

    def _unlink_inheritance_rows_cascaded(self) -> None:
        referrers = self.env.registry.cascades_into_inheritance_trees.get(self._name)
        if not referrers:
            return
        for model_name, path in referrers:
            model = self.env[model_name].sudo().with_context(active_test=False)
            if not model._is_path_in_database(path):
                continue
            rows = model.search([(path, "in", self.ids)])  # noqa: E8507  model varies
            if model_name == self._name:
                rows -= self
            _debug.pipeline(
                "unlink.inheritance_rows_cascaded",
                model=self._name,
                referrer=model_name,
                path=path,
                rows=len(rows),
            )
            rows.unlink()

    def _is_path_in_database(self, path: str) -> bool:
        known = self.pool._paths_in_database
        key = (self._name, path)
        if key in known:
            return True
        model = self
        for name in path.split("."):
            if not column_exists(self.env.cr, model._table, name):
                return False
            model = self.env[model._fields[name].comodel_name]
        # only a column seen is remembered: one missing is created by a later
        # init_models, perhaps in another transaction, and must then be seen
        known.add(key)
        return True

    def _defer_dependent_recomputes(self) -> None:
        # a pending compute that reads these records would run in the flush
        # before the deletion, on values whose own recompute is discarded: it
        # is put off, and _modified_before after the flush asks for it again
        # over the same triggers, once the records are gone
        core = self.env.core
        if not core.has_pending():
            return
        scheduler = core.new_scheduler()
        self._modified_trigger_loop(self._fields, False, scheduler)
        deferred = 0  # debuglog
        for field, ids in scheduler.to_recompute.items():
            pending = core.get_pending_ids(field)
            if waiting := [id_ for id_ in ids if id_ in pending]:
                deferred += len(waiting)  # debuglog
                core.mark_done(field, waiting)
        if _debug.logic.enabled and deferred:
            _debug.logic(
                "unlink.dependent_recomputes_deferred",
                model=self._name,
                records=len(self),
                deferred=deferred,
            )

    def _modified_many2many_corecords(self) -> None:
        # the relation rows go with the records, so each corecord's side of a
        # stored many2many changes too; its dependents hang off the inverse
        # field, which `Many2many.write` reports to them and the records' own
        # trigger tree does not reach
        inverses = self.pool.field_inverses
        triggers = self.pool._get_field_triggers()
        records = self.with_env(self.env._derive(su=True, active_test=False))
        for field in self._fields.values():
            if not (field.is_many2many and field.store):
                continue
            names = [
                invf.name
                for invf in inverses[field]
                if invf.model_name == field.comodel_name and invf in triggers
            ]
            if names and (corecords := records[field.name]):
                _debug.logic(
                    "unlink.many2many_corecords_modified",
                    model=self._name,
                    field=field.name,
                    corecords=len(corecords),
                )
                corecords.modified(names)

    def _discard_pending_recomputes(self) -> None:
        core = self.env.core
        if core.has_pending():
            model_name = self._name
            pending_ids = self._ids
            discarded = 0  # debuglog
            for field in core.get_pending_fields():
                if field.model_name == model_name:
                    discarded += 1  # debuglog
                    core.mark_done(field, pending_ids)
            if _debug.logic.enabled and discarded:
                _debug.logic(
                    "unlink.pending_recomputes_discarded",
                    model=model_name,
                    records=len(pending_ids),
                    fields=discarded,
                )

    def _discard_pending_of_vanished_rows(self, gone: set[str]) -> None:
        # the computes queued on rows a cascade removed with these records
        # (a tree's children included) can never run, nor those queued on the
        # drafts of any removed row, which read what they were not given from
        # it: a flush that tried would compute the gone rows from nothing and
        # cache the result under their ids
        core = self.env.core
        if not core.has_pending():
            return
        pending_by_model: defaultdict[str, list[Field[typing.Any]]] = defaultdict(list)
        for field in core.get_pending_fields():
            if field.model_name in gone:
                pending_by_model[field.model_name].append(field)
        tree = {self._name, *self.env._table_inheritance_tree(self._name)}
        deleted = set(self._ids)
        for model_name, fields in pending_by_model.items():
            known = deleted if model_name in tree else set()
            rows = {
                row
                for field in fields
                for id_ in core.get_pending_ids(field)
                if (row := id_ or id_.origin) and row not in known
            }
            kept = (
                set(self.env[model_name].browse(tuple(rows)).exists()._ids)
                if rows
                else set()
            )
            for field in fields:
                vanished = [
                    id_
                    for id_ in core.get_pending_ids(field)
                    if (row := id_ or id_.origin) and row not in kept
                ]
                if vanished:
                    _debug.logic(
                        "unlink.pending_of_vanished_rows_discarded",
                        model=model_name,
                        field=field.name,
                        records=len(vanished),
                    )
                    core.mark_done(field, vanished)

    def _log_unlinked_ids(self, deleted_ids: list[int]) -> None:
        if len(deleted_ids) <= _UNLINK_LOG_MAX_IDS:
            _unlink.info(
                "User #%s deleted %s records with IDs: %r",
                self.env.uid,
                self._name,
                deleted_ids,
            )
        else:
            _unlink.info(
                "User #%s deleted %s records: %d IDs in [%s..%s], first %d: %r",
                self.env.uid,
                self._name,
                len(deleted_ids),
                min(deleted_ids),
                max(deleted_ids),
                _UNLINK_LOG_MAX_IDS,
                deleted_ids[:_UNLINK_LOG_MAX_IDS],
            )

    def _log_unlink_profile(self, prof: _OrmProfile, record_count: int) -> None:
        prof.report(_orm_crud, "unlink %s: %d records", self._name, record_count)
        if prof.timed and self.env.transaction.observers:
            self.env.transaction.observe_timing(
                "unlink", self._name, record_count, prof.elapsed
            )

    def _invalidate_after_unlink(self) -> None:
        env = self.env
        registry = env.registry
        cascades = registry.models_cascading_from
        # the row a subtype deleted is the row every other model of its
        # table-inheritance tree still holds in cache
        gone = {self._name, *env._table_inheritance_tree(self._name)}
        todo = list(gone)
        while todo:
            for model_name in cascades.get(todo.pop(), ()):
                if model_name not in gone:
                    gone.add(model_name)
                    todo.append(model_name)
        core = env.core
        self._discard_pending_of_vanished_rows(gone)
        core.note_unlinked(gone)
        if core.has_deferred():
            tree = {self._name, *env._table_inheritance_tree(self._name)}
            for model_name in gone:
                core.note_deleted(model_name, self._ids if model_name in tree else None)
        fields_by_comodel = registry.fields_by_comodel
        for model_name in gone:
            for field in env[model_name]._fields.values():
                field._invalidate_cache(env, keep_dirty=True)
            for field in fields_by_comodel.get(model_name, ()):
                field._invalidate_cache(env, keep_dirty=True)
                # a cascade's rows, and the references the database set null
                # to them, change under the ORM: what is computed from them
                # without being stored is read again
                for dependent in registry.get_dependent_fields(field):
                    if not dependent.store:
                        dependent._invalidate_cache(env, keep_dirty=True)
        self._forget_dead_drafts(gone)
        for field in registry.fields_reading_through_a_reference:
            field._invalidate_cache(env, keep_dirty=True)
        _debug.logic(
            "unlink.invalidated_models",
            model=self._name,
            models=len(gone),
            reference_fields=len(registry.fields_reading_through_a_reference),
        )
        Reference.discard_verified_models(env, gone)
        self._invalidate_ref_cache(gone)
        for model_name in gone:
            env[model_name]._access_inputs_written(None)

    def _forget_dead_drafts(self, gone: set[str]) -> None:
        # the drafts of deleted rows are dead: no other draft lists them. The
        # rows a cascade removed are not known by id, so the drafts listed of
        # those models are checked against what still exists
        env = self.env
        tree = {self._name, *env._table_inheritance_tree(self._name)}
        deleted = frozenset(self._ids)
        for model_name in gone:
            fields = [
                typing.cast("_RelationalMulti", field)
                for field in env.registry.fields_by_comodel.get(model_name, ())
                if field.is_x2many
            ]
            if not fields:
                continue
            if model_name in tree:
                origins = deleted
            else:
                listed = set().union(
                    *(field._get_listed_draft_origins(env) for field in fields)
                )
                if not listed:
                    continue
                rows = env[model_name].sudo().with_context(active_test=False)
                origins = frozenset(listed - set(rows.browse(listed).exists()._ids))
                if not origins:
                    continue
            for field in fields:
                field._forget_drafts_of(env, origins)

    def _invalidate_ref_cache(self, model_names: typing.Iterable[str]) -> None:
        names = set(model_names)
        keys = self.env.transaction.forget_refs_of(names)
        if _debug.logic.enabled and keys:
            _debug.logic(
                "unlink.ref_cache_evicted",
                model=self._name,
                models=len(names),
                keys=keys,
            )

    def _unlink_process_batch(self, sub_ids: tuple[int, ...]) -> None:
        self.env.backend.unlink_rows(self, sub_ids)
        _debug.perf.count("unlink.batch", model=self._name, records=len(sub_ids))
