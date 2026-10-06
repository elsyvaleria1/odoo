import threading
import uuid

import psycopg

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFirstContactRace(TransactionCase):
    def test_a_concurrent_first_message_is_retried_not_duplicated(self):
        tag = uuid.uuid4().hex[:12]
        ids = {}
        outcome = {}
        snapshot_taken = threading.Event()
        first_created = threading.Event()
        try:
            with self.leave_registry_test_mode():
                with self.registry.cursor() as cr:
                    env = self.env(cr=cr)
                    domain = env["mail.alias.domain"].create(
                        {"name": f"race-{tag}.example.com"}
                    )
                    inbox = env["mail.inbox"].create(
                        {
                            "name": f"Race {tag}",
                            "kind": "shared",
                            "alias_name": "race",
                            "alias_domain_id": domain.id,
                            "user_ids": [Command.set(env.ref("base.user_admin").ids)],
                        }
                    )
                    partner = env["res.partner"].create(
                        {"name": "Racer", "email": f"racer-{tag}@example.org"}
                    )
                    ids.update(domain=domain.id, inbox=inbox.id, partner=partner.id)

                def first_message():
                    with self.registry.cursor() as cr:
                        env = self.env(cr=cr)
                        snapshot_taken.wait(10)
                        channel = (
                            env["mail.inbox"]
                            .browse(ids["inbox"])
                            ._get_or_create_channel(
                                env["res.partner"].browse(ids["partner"])
                            )
                        )
                        env.flush_all()
                        first_created.set()
                        outcome["first"] = channel.id

                def second_message():
                    with self.registry.cursor() as cr:
                        env = self.env(cr=cr)
                        # its snapshot predates the first message's channel
                        env["discuss.channel"].search_count([])
                        snapshot_taken.set()
                        first_created.wait(10)
                        try:
                            env["mail.inbox"].browse(
                                ids["inbox"]
                            )._get_or_create_channel(
                                env["res.partner"].browse(ids["partner"])
                            )
                            env.flush_all()
                        except psycopg.errors.SerializationFailure:
                            outcome["second"] = "retried"
                            cr.rollback()
                        else:
                            outcome["second"] = "created"

                threads = [
                    threading.Thread(target=second_message),
                    threading.Thread(target=first_message),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(30)
                with self.registry.cursor() as cr:
                    cr.execute(
                        "SELECT count(*) FROM discuss_channel WHERE inbox_id = %s",
                        [ids["inbox"]],
                    )
                    channels = cr.fetchone()[0]
            self.assertEqual(
                outcome.get("second"),
                "retried",
                "the second first-message must fail to serialise, so its "
                "transaction is retried and finds the conversation",
            )
            self.assertEqual(channels, 1)
        finally:
            with self.leave_registry_test_mode(), self.registry.cursor() as cr:
                env = self.env(cr=cr)
                if ids:
                    env["discuss.channel"].search(
                        [("inbox_id", "=", ids["inbox"])]
                    ).unlink()
                    env["mail.inbox"].browse(ids["inbox"]).unlink()
                    env["res.partner"].browse(ids["partner"]).unlink()
                    env["mail.alias.domain"].browse(ids["domain"]).unlink()
