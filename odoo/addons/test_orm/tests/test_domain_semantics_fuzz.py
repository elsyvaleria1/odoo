from collections.abc import Iterator
from contextlib import contextmanager

from odoo.orm.model_test_env import ModelRegistry, model_test_env
from odoo.tests import TransactionCase, tagged
from odoo.tests.domain_fuzz import (
    ITEM_MODELS,
    ITEM_ROOTS,
    LANGS,
    Campaign,
    Dataset,
    Loaded,
    Node,
    Outcome,
    Schema,
    Viewpoint,
    build_schema,
    draw_viewpoint,
    evaluators,
    item_sizes,
    seeds_from_environment,
)

from odoo.addons.test_orm.models import test_domain_semantics as semantics


@tagged("post_install", "-at_install")
class TestDomainSemanticsFuzz(TransactionCase):
    """The domain differential of `odoo.tests.domain_fuzz` on PostgreSQL.

    Each seed draws a dataset over the `test_orm.domain.*` models and a
    viewpoint: `en_US` or `fr_FR` (the translated fields hold a value in
    each), a time zone the date parts read, and, in the user campaigns, a user
    whose group holds random `ir.access` permissions and guards. Every domain
    is answered by the SQL search, by `filtered_domain` over the records the
    evaluator reads, by its conditions searched alone and combined as sets,
    by the in-memory backend (superuser viewpoints) and, for a user's domain
    reading no ruled model but the root, by the superuser's search among the
    user's records.

    `ODOO_DOMAIN_FUZZ_ROUNDS=<n>` runs n seeds from `ODOO_DOMAIN_FUZZ_SEED`
    (0 by default); `ODOO_DOMAIN_FUZZ_DEPTH` nests the domains deeper.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("fr_FR")

    def _campaign(
        self, *, active_test: bool, merges: bool, as_user: bool = False
    ) -> Campaign:
        registry = ModelRegistry(
            [
                semantics.TestOrmDomainPartner,
                semantics.TestOrmDomainTag,
                semantics.TestOrmDomainItem,
                semantics.TestOrmDomainLine,
                semantics.TestOrmDomainDetail,
            ],
            isolated=True,
        )
        registry.ilike_normalizer = self.env.registry.get_ilike_normalizer(self.env)
        schema = build_schema(self.env, ITEM_MODELS)
        env = self.env

        @contextmanager
        def world(dataset: Dataset, viewpoint: Viewpoint) -> Iterator:
            savepoint = env.cr.savepoint()
            try:
                loaded = Loaded(
                    env, schema, dataset, active_test=active_test, viewpoint=viewpoint
                )
                on_postgres = evaluators(loaded)
                if viewpoint.rules is not None:
                    yield on_postgres, loaded
                    return
                with model_test_env(
                    registry=registry, langs=LANGS, check_cache=False
                ) as memory:
                    in_memory = Loaded(
                        memory,
                        schema,
                        dataset,
                        active_test=active_test,
                        viewpoint=viewpoint,
                    )

                    def evaluate(model: str, node: Node) -> dict[str, Outcome]:
                        outcomes = on_postgres(model, node)
                        outcomes["memory search"] = in_memory.search(
                            model, in_memory.domain(node)
                        )
                        return outcomes

                    yield evaluate, loaded
            finally:
                savepoint.close(rollback=True)
                env.invalidate_all()

        def viewpoints(schema: Schema, dataset: Dataset, rng) -> Viewpoint:
            return draw_viewpoint(
                schema, dataset, rng, rules=as_user, root="test_orm.domain.item"
            )

        return Campaign(
            schema,
            ITEM_ROOTS,
            world,
            item_sizes,
            domains_per_seed=100,
            merges=merges,
            viewpoints=viewpoints,
        )

    def _assert_agree(
        self, *, active_test: bool = False, merges: bool = False, as_user=False
    ):
        campaign = self._campaign(
            active_test=active_test, merges=merges, as_user=as_user
        )
        shrunk = campaign.run(seeds_from_environment(range(40)))
        if campaign.findings:
            self.fail(campaign.describe(shrunk))

    def test_search_filtered_domain_the_memory_backend_and_the_set_algebra_agree(self):
        self._assert_agree()

    def test_they_agree_on_the_active_records_and_relations(self):
        self._assert_agree(active_test=True)

    def test_they_agree_on_conditions_the_optimizer_merges(self):
        self._assert_agree(merges=True)

    def test_they_agree_for_a_user_under_random_access_rules(self):
        self._assert_agree(as_user=True)

    def test_they_agree_for_a_user_on_the_active_records(self):
        self._assert_agree(active_test=True, as_user=True)
