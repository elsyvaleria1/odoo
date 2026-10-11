import logging
import threading
import time

import psycopg.errors

from odoo.service.transaction import retrying
from odoo.tests import TransactionCase
from odoo.tools import SQL, mute_logger

_logger = logging.getLogger(__name__)


def _id_marks(cr):
    cr.execute(
        """
        SELECT t.relname, COALESCE(pg_sequence_last_value(s.oid), 0)
          FROM pg_class s
          JOIN pg_depend d ON d.objid = s.oid
                          AND d.classid = 'pg_class'::regclass
                          AND d.refclassid = 'pg_class'::regclass
                          AND d.deptype IN ('a', 'i')
          JOIN pg_class t ON t.oid = d.refobjid
          JOIN pg_attribute a ON a.attrelid = t.oid
                             AND a.attnum = d.refobjsubid
                             AND a.attname = 'id'
         WHERE s.relkind = 'S'
           AND t.relkind = 'r'
           AND t.relnamespace = 'public'::regnamespace
           AND t.relname NOT LIKE 'orm_signaling%%'
        """
    )
    return dict(cr.fetchall())


class PosRaceCase(TransactionCase):
    @mute_logger("odoo.db.cursor")
    def _drop_rows_committed_since(self, marks):
        with self.leave_registry_test_mode(), self.registry.cursor() as cr:
            pending = {
                table
                for table, last_id in _id_marks(cr).items()
                if last_id > marks.get(table, 0)
            }
            while pending:
                dropped = set()
                for table in sorted(pending):
                    try:
                        with cr.savepoint(flush=False):
                            cr.execute(
                                SQL(
                                    "DELETE FROM %s WHERE id > %s",
                                    SQL.identifier(table),
                                    marks.get(table, 0),
                                )
                            )
                    except (
                        psycopg.errors.ForeignKeyViolation,
                        psycopg.errors.RestrictViolation,
                    ):
                        continue
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    dropped.add(table)
                if not dropped:
                    raise AssertionError(
                        f"rows committed by the test are still referenced: {sorted(pending)}"
                    )
                pending -= dropped
            cr.commit()

    def _env(self, cr):
        return self.env(cr=cr, user=self.admin_id)

    def _drop_rows_committed_from_now(self):
        with self.registry.cursor() as cr:
            marks = _id_marks(cr)
        self.addCleanup(self._drop_rows_committed_since, marks)

    def _is_waiting_on_a_lock(self, cr, pid):
        cr.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid = %s AND NOT granted)",
            [pid],
        )
        return cr.fetchone()[0]

    def _race(self, first, second):
        first_worked = threading.Event()
        first_committed = threading.Event()
        attempts = []
        outcome = {}
        with (
            self.registry.cursor() as cr_first,
            self.registry.cursor() as cr_second,
        ):
            env_first, env_second = self._env(cr_first), self._env(cr_second)
            cr_second.execute("SELECT pg_backend_pid()")
            second_pid = cr_second.fetchone()[0]

            def attempt():
                attempts.append(len(attempts) + 1)
                (first_worked if len(attempts) == 1 else first_committed).wait(30)
                return second(env_second)

            def run_second():
                try:
                    outcome["result"] = retrying(attempt, env_second)
                except Exception as error:
                    outcome["error"] = error

            thread = threading.Thread(target=run_second)
            thread.start()
            try:
                first(env_first)
                env_first.flush_all()
            finally:
                first_worked.set()
            waited = False
            deadline = time.monotonic() + 15
            while (
                thread.is_alive() and len(attempts) < 2 and time.monotonic() < deadline
            ):
                if self._is_waiting_on_a_lock(cr_first, second_pid):
                    waited = True
                    break
                time.sleep(0.02)
            cr_first.commit()
            first_committed.set()
            thread.join(60)
        _logger.debug(
            "race: waited=%s attempts=%s outcome=%s", waited, len(attempts), outcome
        )
        return waited, len(attempts), outcome
