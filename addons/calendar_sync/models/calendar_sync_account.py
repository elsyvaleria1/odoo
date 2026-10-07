import logging
import uuid
from datetime import UTC, timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import LockError
from odoo.fields import Domain
from odoo.modules.registry import Registry
from odoo.tools import frozendict, str2bool

from odoo.addons.calendar_sync.remote import (
    PERMANENT,
    CalendarSyncError,
    ErrorKind,
    RemoteEvent,
    RemoteKind,
)

_logger = logging.getLogger(__name__)

# what one push sends at most; the rest waits for the next run
PUSH_BUDGET = 200


class CalendarSyncAccount(models.Model):
    """One user's synchronization with one provider: where it stands, beside
    the user's own connection to the provider, which holds the tokens."""

    _name = "calendar.sync.account"
    _description = "Calendar Synchronization Account"
    _order = "user_id, provider"

    _access_anchors = frozendict(
        {
            "owner": models.Anchor("user_id", shared=False),
            "company": models.Anchor("user_id.company_id", shared=False),
        }
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        required=True,
        ondelete="cascade",
    )
    provider = fields.Selection(
        selection=[],
        required=True,
    )
    sync_token = fields.Char(
        string="Next Sync Token",
        copy=False,
        classification="secret.credential",
        groups="base.group_system",
        help="Where the provider's next change list starts; empty asks for a full one.",
    )
    stopped = fields.Boolean(
        string="Synchronization Stopped",
        copy=False,
        help="The user stopped this synchronization; nothing is sent or read.",
    )
    last_sync_date = fields.Datetime(
        string="Last Synchronization",
        copy=False,
    )
    insert_since = fields.Datetime(
        string="Send Events Created Since",
        copy=False,
        help="Events created before this date are not sent to the provider.",
    )

    _user_provider_unique = models.Constraint(
        "UNIQUE(user_id, provider)",
        "A user synchronizes with a provider once.",
    )

    @api.model
    def _calendar_sync_providers(self) -> dict:
        """{code: CalendarSyncProvider} of the installed adapters."""
        return {}

    @api.model
    def _provider(self, code: str):
        return self._calendar_sync_providers()[code]

    @api.model
    def _find(self, user, code: str):
        """`user`'s account with `code`, elevated, empty when none exists."""
        return self.sudo().search(
            [("user_id", "=", user.id), ("provider", "=", code)], limit=1
        )

    @api.model
    def _for(self, user, code: str):
        """`user`'s account with `code`, created on first use, elevated."""
        return self._find(user, code) or self.sudo().create(
            {"user_id": user.id, "provider": code}
        )

    @api.model
    def _is_paused(self, code: str) -> bool:
        return str2bool(
            self.env.registry.settings.get(
                self.env, self._provider(code).paused_param, False
            ),
            default=False,
        )

    @api.model
    def _set_paused(self, code: str, paused: bool) -> None:
        self.env["ir.config_parameter"].sudo().set_param(
            self._provider(code).paused_param, paused
        )

    @api.model
    def _has_client(self, code: str) -> bool:
        return self.env.ref(self._provider(code).service)._has_oauth_client()

    @api.model
    def _cron_sync(self) -> None:
        """Every account whose user authorized it and did not stop it, provider
        by provider, a commit per user."""
        Users = self.env["res.users"]
        for code in self._calendar_sync_providers():
            if self._is_paused(code):
                continue
            for user in Users._calendar_sync_candidates(code):
                Users._calendar_sync_run_for_cron(user, code)

    # -- the engine: what a provider with an adapter gets ---------------------

    def _adapter(self):
        self.check_singleton()
        return self._adapter_of(self.provider)

    @api.model
    def _adapter_of(self, code: str):
        return self.env[self._provider(code).adapter]

    @api.model
    def _engine_providers(self) -> dict:
        """{code: provider} of the providers the engine runs."""
        return {
            code: provider
            for code, provider in self._calendar_sync_providers().items()
            if provider.adapter
        }

    def _window(self) -> Domain:
        """The events this account synchronizes: its user's, around today."""
        self.check_singleton()
        provider = self._provider(self.provider)
        days = 365
        if provider.range_param:
            days = int(
                self.env.registry.settings.get(self.env, provider.range_param, False)
                or days
            )
        now = fields.Datetime.now()
        return (
            Domain("partner_ids.user_ids", "in", self.user_id.id)
            & Domain("stop", ">", now - timedelta(days=days))
            & Domain("start", "<", now + timedelta(days=days))
            # the series is sent for the events that follow it
            & ~(
                Domain("recurrency", "=", True)
                & Domain("recurrence_id", "!=", False)
                & Domain("follow_recurrence", "=", True)
            )
        )

    @api.model
    def _actives(self, code: str):
        return _Actives(self, code)

    @api.model
    def _writer(self, record, code: str, running=None, active=None):
        """The account a change of `record` goes out through: its organizer's
        while the organizer synchronizes with `code`, else `running`.
        `active`, an _Actives of `code`, saves asking twice of a user."""
        active = active or _Actives(self, code)
        organizer = (
            record.user_id
            if record._name == "calendar.event"
            else record.base_event_id.user_id
        )
        if organizer and active(organizer):
            return active.account(organizer)
        return running or self.browse()

    @api.model
    def _may_insert(self, record, code: str, active=None) -> bool:
        """An event goes to the provider through its organizer, or through any
        attendee when it has none; an event of a series goes as the series,
        and one marked recurring whose series is not made yet waits for it."""
        if record._name == "calendar.event":
            if record.follow_recurrence if record.recurrence_id else record.recurrency:
                return False
            organizer = record.user_id
        else:
            organizer = record.base_event_id.user_id
        return not organizer or (active or _Actives(self, code))(organizer)

    def _calendar_sync(self) -> bool:
        """Read this account's calendar into Odoo, then send what Odoo holds
        and the calendar does not; whether anything was read."""
        read = self._read()
        if read is None:
            return False
        changes, applied = read
        # a first or repaired synchronization does not mail every attendee
        self._queue_push(quiet=changes.full)
        return bool(applied)

    def _read(self):
        """Read this account's calendar into Odoo: (the changes read, the
        records they changed), or None when the synchronization is not
        running or runs already."""
        self.check_singleton()
        if not self.user_id._calendar_sync_active(self.provider):
            return None
        try:
            self.lock_for_update(allow_referencing=True)
        except LockError:
            _logger.info("calendar sync of %s is running already", self.user_id.login)
            return None
        adapter = self._adapter()
        try:
            changes = adapter._list_changes(self, self.sync_token or None)
        except CalendarSyncError as error:
            if error.kind != ErrorKind.TOKEN_INVALID:
                raise
            changes = adapter._list_changes(self, None)
        applied = self._pull(changes)
        values = {"last_sync_date": fields.Datetime.now()}
        if changes.next_token:
            values["sync_token"] = changes.next_token
        self.write(values)
        return changes, applied

    # -- pull ----------------------------------------------------------------

    def _pull(self, changes) -> list:
        """Apply `changes` to Odoo; the records they changed. The series go
        first: applying one links its events, which the items after it may be."""
        self.check_singleton()
        code = self.provider
        adapter = self._adapter()
        Link = self.env["calendar.sync.link"]._engine()
        links = Link._match(self, changes.events)
        # the write dates before this pull: applying one item may write
        # another record, which must not make its own update look older
        written = {
            link._record(): link._record().write_date
            for link in links.values()
            if link._record()
        }
        applying = self.with_context(
            calendar_sync_applying=code,
            dont_notify=True,
            no_mail_to_attendees=True,
            skip_contact_description=True,
        )
        masters = {
            remote.remote_id: remote
            for remote in changes.events
            if remote.kind == RemoteKind.SERIES
        }
        occurrences = {}
        for remote in changes.events:
            if remote.kind == RemoteKind.OCCURRENCE and remote.master_id in masters:
                occurrences.setdefault(remote.master_id, []).append(remote)
        rest = [
            remote
            for remote in changes.events
            if remote.remote_id not in masters
            and not (
                remote.kind == RemoteKind.OCCURRENCE and remote.master_id in masters
            )
        ]

        def pull(remote):
            return self._pull_one(
                applying, adapter, remote, links, written, occurrences
            )

        applied = [record for remote in masters.values() if (record := pull(remote))]
        if masters:
            # applying a series may have deleted events: an item of one is
            # no longer Odoo's to apply; or linked them, to items found now
            gone = {rid for rid, link in links.items() if not link.exists()}
            rest = [remote for remote in rest if remote.remote_id not in gone]
            for remote_id in gone:
                del links[remote_id]
            links |= Link._match(
                self, [remote for remote in rest if remote.remote_id not in links]
            )
        applied += [record for remote in rest if (record := pull(remote))]
        return applied

    def _pull_one(self, applying, adapter, remote, links, written, occurrences):
        """Apply `remote`; its record when it changed one."""
        link = links.get(remote.remote_id)
        record = link._record() if link else None
        if link and not record:
            return None
        if (
            remote.kind == RemoteKind.SERIES
            and record
            and record._name != "calendar.recurrence"
        ):
            # an event that became a series under the same id: the adapter
            # makes the series of it
            link, record = None, None
        if remote.cancelled:
            if record:
                applying._cancel(link)
            return record
        if record and not self._is_newer(
            remote, link, written.get(record, record.write_date)
        ):
            return None
        if remote.kind == RemoteKind.SERIES:
            record = applying._apply_series(
                remote, occurrences.get(remote.remote_id, []), record
            )
        elif record:
            record.with_env(applying.env).write(
                adapter._odoo_values(remote, record._name, record)
            )
        else:
            record = applying.env["calendar.event"].create(
                adapter._odoo_values(remote, "calendar.event", None)
            )
        self._applied(
            self.env["calendar.sync.link"]._engine()._adopt(self, record, remote),
            remote,
        )
        return record

    @api.model
    def _is_newer(self, remote, link, written) -> bool:
        """Whether `remote` changed since Odoo last heard of it, and later
        than Odoo changed its record."""
        if link.remote_etag and remote.etag == link.remote_etag:
            return False
        if not written or not remote.updated:
            return True
        updated = remote.updated
        if updated.tzinfo:
            updated = updated.astimezone(UTC).replace(tzinfo=None)
        return updated >= written

    def _applied(self, link, remote) -> None:
        """`link`'s record holds what the provider holds: nothing to send."""
        link.remote_etag = remote.etag
        self.env["calendar.sync.link"]._of(link._record(), self.provider).write(
            {"pending": False, "error": False}
        )

    def _apply_series(self, master, occurrences, recurrence):
        recurrence, events = self._adapter()._apply_series(
            self, master, occurrences, recurrence or self.env["calendar.recurrence"]
        )
        Link = self.env["calendar.sync.link"]._engine()
        by_id = {remote.remote_id: remote for remote in occurrences}
        for remote_id, event in events.items():
            if remote := by_id.get(remote_id):
                self._applied(Link._adopt(self, event, remote), remote)
        return recurrence

    def _cancel(self, link) -> None:
        """The item of `link` was deleted from this account's calendar: its
        organizer's record goes, an attendee declines."""
        record = link._record()
        link.unlink()
        if record._name == "calendar.recurrence":
            events, organizer = record.calendar_event_ids, record.base_event_id.user_id
        else:
            events, organizer = record, record.user_id
        if organizer == self.user_id:
            # gone from every calendar of the provider with its organizer's
            self.env["calendar.sync.link"]._of(record, self.provider).unlink()
            self.env["calendar.sync.link"]._of(events, self.provider).unlink()
            events.unlink()
            record.exists().unlink()
            return
        events.attendee_ids.filtered(
            lambda attendee: attendee.partner_id == self.user_id.partner_id
        ).state = "declined"

    # -- push ----------------------------------------------------------------

    def _queue_push(self, records=None, quiet=False) -> None:
        """Send what these accounts owe their calendars once this transaction
        is committed, an insert's id being committed before it is sent:
        `records` alone, as an edit in the interface waits for them, or all
        of it, as a run does. `quiet` sends no invitation or update mails."""
        data = self.env.cr.postcommit.data
        if "calendar_sync.push" not in data:
            data.setdefault_set("calendar_sync.push")
            data.setdefault_set("calendar_sync.push.records")
            data.setdefault_set("calendar_sync.push.quiet")
            data.setdefault_set("calendar_sync.push.deletes")
            cr, dbname, uid = self.env.cr, self.env.cr.dbname, self.env.uid

            @cr.postcommit.add
            def push():
                everything = cr.postcommit.data.pop("calendar_sync.push")
                records = cr.postcommit.data.pop("calendar_sync.push.records")
                quiet = cr.postcommit.data.pop("calendar_sync.push.quiet")
                deletes = cr.postcommit.data.pop("calendar_sync.push.deletes")
                only = dict.fromkeys(deletes, ())
                for account_id, model, record_id in records:
                    only[account_id] = (*only.get(account_id, ()), (model, record_id))
                with Registry(dbname).cursor() as push_cr:
                    env = api.Environment(push_cr, uid, {})
                    for account in (
                        env["calendar.sync.account"]
                        ._as_engine()
                        .browse(sorted({*everything, *only}))
                        .exists()
                    ):
                        owner = account.user_id._calendar_sync_as_owner()
                        try:
                            account.with_env(owner.env).with_context(
                                calendar_sync_quiet=account.id in quiet,
                                calendar_sync_interactive=account.id not in everything,
                            )._push(
                                None if account.id in everything else only[account.id]
                            )
                            push_cr.commit()
                        except Exception:
                            _logger.exception("calendar push of %s failed", account)
                            push_cr.rollback()

        if records is None:
            data["calendar_sync.push"].update(self.ids)
        elif not records:
            # the deletions alone: the push starts with them
            data["calendar_sync.push.deletes"].update(self.ids)
        else:
            data["calendar_sync.push.records"].update(
                (account.id, record._name, record.id)
                for account in self
                for record in records
            )
        if quiet:
            data["calendar_sync.push.quiet"].update(self.ids)

    def _as_engine(self):
        """These accounts as the engine reads them, whoever it runs as."""
        return self.with_privilege(
            "calendar_sync.privilege_engine",
            reason="the engine synchronizes the accounts' calendars",
        )

    def _push(self, only=None) -> None:
        """Send this account's calendar what Odoo changed: deletions, changes,
        then new records, committing after each; of the records, `only` those
        [(model, id)] when given."""
        self.check_singleton()
        code = self.provider
        if not self.user_id._calendar_sync_active(code):
            return
        Link = self.env["calendar.sync.link"]._engine()
        budget = PUSH_BUDGET
        for tombstone in Link.search(
            [
                ("account_id", "=", self.id),
                ("event_id", "=", False),
                ("recurrence_id", "=", False),
            ]
        ):
            if budget <= 0 or not self._send_delete(tombstone):
                return
            budget -= 1
        others = {}
        for record, writer in self._to_push(only):
            if writer != self:
                others[writer] = others.get(writer, record.browse()) | record
                continue
            if budget <= 0 or not self._send(record):
                break
            budget -= 1
        for writer, records in others.items():
            writer._queue_push(None if only is None else records)

    def _to_push(self, only=None):
        """[(record, writer)] of what Odoo owes the calendars of this account's
        provider and this account may send: the records whose links wait to
        be sent, then its events and series no calendar of the provider has;
        of `only` [(model, id)] when given, those of them."""
        code = self.provider
        Link = self.env["calendar.sync.link"]._engine()
        active = _Actives(self, code)
        if only is not None:
            records = []
            for model, record_id in only:
                record = self.env[model].browse(record_id).exists()
                links = record and Link._of(record, code)
                if (
                    links.filtered("pending")
                    if links
                    else record
                    and record.active
                    and self._may_insert(record, code, active)
                ):
                    records.append(record)
            return [
                (record, self._writer(record, code, self, active)) for record in records
            ]
        pending = Link.search(
            [
                ("account_id.provider", "=", code),
                ("pending", "=", True),
                ("error", "=", False),
                "|",
                ("event_id", "!=", False),
                ("recurrence_id", "!=", False),
            ]
        )
        records = list(dict.fromkeys(link._record() for link in pending))
        unlinked = Domain(
            "calendar_sync_link_ids", "not any", [("account_id.provider", "=", code)]
        )
        created = (
            Domain("create_date", ">=", self.insert_since)
            if self.insert_since
            else Domain.TRUE
        )
        events = (
            self.env["calendar.event"]
            .with_env(Link.env)
            .search(self._window() & unlinked & created, limit=PUSH_BUDGET)
        )
        series = (
            self.env["calendar.recurrence"]
            .with_env(Link.env)
            .search(
                Domain("base_event_id.user_id", "=", self.user_id.id)
                & Domain("rrule", "!=", False)
                & unlinked
                & created,
                limit=PUSH_BUDGET,
            )
        )
        records += [
            record
            for record in (*series, *events)
            if self._may_insert(record, code, active)
        ]
        return [
            (record, self._writer(record, code, self, active)) for record in records
        ]

    def _call(self, operation, *args):
        """(result, None), or (None, the error) when the provider refused."""
        try:
            return operation(*args), None
        except CalendarSyncError as error:
            return None, error
        except Exception as error:
            _logger.warning("calendar %s: %s", self.provider, error, exc_info=True)
            return None, self._adapter()._classify(error)

    def _send_delete(self, tombstone) -> bool:
        """Delete `tombstone`'s item; whether the push goes on."""
        if not tombstone.remote_id:
            tombstone.unlink()
            return True
        __, error = self._call(self._adapter()._delete, self, tombstone.remote_id)
        if error and error.kind in (ErrorKind.AUTH, ErrorKind.THROTTLED):
            return False
        if not error or error.kind == ErrorKind.GONE or error.kind in PERMANENT:
            tombstone.unlink()
        self.env.cr.commit()
        return True

    def _send(self, record) -> bool:
        """Send `record` to this account's calendar; whether the push goes on."""
        Link = self.env["calendar.sync.link"]._engine()
        adapter = self._adapter()
        record = record.with_env(self.env)
        own = Link.search(
            [
                ("account_id", "=", self.id),
                (
                    "recurrence_id"
                    if record._name == "calendar.recurrence"
                    else "event_id",
                    "=",
                    record.id,
                ),
            ]
        )
        if not own.remote_id and Link._of(record, self.provider) - own:
            own = self._resolve(record, own)
            if not own:
                return True
        if not record.active:
            if own.remote_id:
                __, error = self._call(adapter._delete, self, own.remote_id)
                if error and error.kind not in (ErrorKind.GONE, *PERMANENT):
                    return self._failed(own, record, error)
            Link._of(record, self.provider).unlink()
        elif not (values := adapter._remote_values(record, self)):
            # nothing the provider can hold yet: a series with no event
            return True
        elif own.remote_id:
            remote, error = self._call(
                adapter._patch, self, own.remote_id, record, values
            )
            if error:
                return self._failed(own, record, error)
            own.remote_etag = remote and remote.etag
            Link._of(record, self.provider).pending = False
        else:
            if own.error:
                return True
            own = own or Link.create(
                {
                    "account_id": self.id,
                    (
                        "recurrence_id"
                        if record._name == "calendar.recurrence"
                        else "event_id"
                    ): record.id,
                    "insert_id": uuid.uuid4().hex,
                    "pending": True,
                }
            )
            # the insert id is kept before it is sent: a retry sends it again
            self.env.cr.commit()
            remote, error = self._call(
                adapter._insert, self, record, values, own.insert_id
            )
            if (
                error
                and error.kind == ErrorKind.CONFLICT
                and self._provider(self.provider).capabilities.client_insert_id
            ):
                own.write({"remote_id": own.insert_id, "pending": False})
            elif error:
                return self._failed(own, record, error)
            else:
                own.write(
                    {
                        "remote_id": remote.remote_id,
                        "universal_id": remote.universal_id,
                        "remote_etag": remote.etag,
                        "pending": False,
                    }
                )
                adapter._after_insert(self, record, remote)
        self.env.cr.commit()
        return True

    def _resolve(self, record, own):
        """This account's link of a `record` another account's calendar holds:
        that account's id when ids are shared, else this calendar's copy of
        the item, looked up by its iCalendar UID; empty when it has none."""
        Link = self.env["calendar.sync.link"]._engine()
        others = Link._of(record, self.provider) - own
        source = others.filtered("remote_id")[:1]
        if not source:
            return own
        if self._provider(self.provider).capabilities.shared_ids:
            return Link._adopt(self, record, RemoteEvent(source.remote_id), source)
        if not source.universal_id:
            return own
        remote, error = self._call(self._adapter()._find, self, source.universal_id)
        if error or not remote:
            return own
        return Link._adopt(self, record, remote, source)

    def _failed(self, link, record, error) -> bool:
        """Apply the engine's rule for `error`; whether the push goes on."""
        if error.kind in (ErrorKind.AUTH, ErrorKind.THROTTLED):
            return False
        if error.kind in PERMANENT:
            link.error = error.message
            self.env["calendar.sync.link"]._of(record, self.provider).pending = False
            self._note_refusal(record, error)
        elif error.kind == ErrorKind.GONE and link.remote_id:
            if self._provider(self.provider).capabilities.shared_ids:
                link.pending = False
            else:
                link.unlink()
        self.env.cr.commit()
        return True

    def _note_refusal(self, record, error) -> None:
        event = (
            record.base_event_id if record._name == "calendar.recurrence" else record
        )
        label = self._provider(self.provider).label
        event.message_post(
            body=Markup("%s<br/>%s")
            % (
                self.env._(
                    "%(provider)s refused this event; it is not sent again until it changes.",
                    provider=label,
                ),
                error.message,
            ),
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )


class _Actives:
    """Whether users synchronize with one provider, and their accounts, each
    asked once of a user."""

    def __init__(self, Account, code: str) -> None:
        self.Account, self.code = Account, code
        self._active, self._accounts = {}, {}

    def __call__(self, user) -> bool:
        if user.id not in self._active:
            self._active[user.id] = user._calendar_sync_active(self.code)
        return self._active[user.id]

    def account(self, user):
        if user.id not in self._accounts:
            self._accounts[user.id] = self.Account._for(user, self.code)
        return self._accounts[user.id]
