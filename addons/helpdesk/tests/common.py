from contextlib import contextmanager
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.tests.common import TransactionCase

from odoo.addons.mail.tests.common import MockEmail


@contextmanager
def patch_now(env, when):
    """Freeze the wall clock and the transaction clock at ``when``.

    ``when`` is a datetime or a ``'%Y-%m-%d %H:%M:%S'`` string; most call sites
    pass the string. ``cr.now()`` is contractually a ``datetime`` and its
    consumers do datetime arithmetic on it -- ``_get_notification_scheduled_date``
    reads ``.tzinfo`` -- so the string has to be parsed here rather than handed
    through, otherwise any tracked write that posts a message inside the block
    dies on ``'str' object has no attribute 'tzinfo'``.
    """
    frozen = fields.Datetime.to_datetime(when)
    with freeze_time(frozen), patch.object(env.cr, "now", lambda: frozen):
        yield
        env.flush_all()


class HelpdeskCommon(TransactionCase, MockEmail):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._init_mail_gateway()
        cls.env.user.tz = "Europe/Brussels"
        cls.env["resource.calendar"].search(
            [("schedule_type", "=", "fully_fixed")]
        ).write({"tz": "Europe/Brussels"})

        # we create a helpdesk user and a manager
        Users = cls.env["res.users"].with_context(tracking_disable=True)
        cls.main_company_id = cls.env.user.company_id.id
        cls.partner = cls.env["res.partner"].create({"name": "Customer Credee"})

        cls.helpdesk_manager = Users.create(
            {
                "company_id": cls.main_company_id,
                "name": "Helpdesk Manager",
                "login": "hm",
                "email": "hm@example.com",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("helpdesk.group_helpdesk_manager").id,
                            cls.env.ref("base.group_partner_manager").id,
                        ],
                    )
                ],
                "tz": "Europe/Brussels",
            }
        )
        cls.helpdesk_user = Users.create(
            {
                "company_id": cls.main_company_id,
                "name": "Helpdesk User",
                "login": "hu",
                "email": "hu@example.com",
                "group_ids": [(6, 0, [cls.env.ref("helpdesk.group_helpdesk_user").id])],
                "tz": "Europe/Brussels",
            }
        )
        cls.helpdesk_portal = Users.create(
            {
                "company_id": cls.main_company_id,
                "name": "Helpdesk Portal",
                "login": "hp",
                "email": "hp@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
                "tz": "Europe/Brussels",
            }
        )
        # the manager defines a team for our tests (the .sudo() at the end is to avoid potential uid problems)
        cls.test_team = (
            cls.env["team.team"]
            .with_user(cls.helpdesk_manager)
            .create({"use_helpdesk": True, "name": "Test Team"})
            .sudo()
        )
        cls.test_team.helpdesk_stage_ids = False
        # He then defines its stages
        stage_as_manager = cls.env["helpdesk.stage"].with_user(cls.helpdesk_manager)
        cls.stage_new = stage_as_manager.create(
            {
                "name": "New",
                "sequence": 10,
                "team_ids": [(4, cls.test_team.id, 0)],
            }
        )
        cls.stage_progress = stage_as_manager.create(
            {
                "name": "In Progress",
                "sequence": 20,
                "team_ids": [(4, cls.test_team.id, 0)],
            }
        )
        cls.stage_done = stage_as_manager.create(
            {
                "name": "Done",
                "sequence": 30,
                "team_ids": [(4, cls.test_team.id, 0)],
                "fold": True,
            }
        )
        cls.stage_cancel = stage_as_manager.create(
            {
                "name": "Cancelled",
                "sequence": 40,
                "team_ids": [(4, cls.test_team.id, 0)],
                "fold": True,
            }
        )

    @contextmanager
    def _ticket_patch_now(self, when):
        with patch_now(self.env, when):
            yield

    def flush_tracking(self):
        """Force the creation of tracking values."""
        self.env.flush_all()
        self.cr.flush()
