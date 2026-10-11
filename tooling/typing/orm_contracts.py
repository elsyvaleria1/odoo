from typing import TYPE_CHECKING, Literal, assert_type

if TYPE_CHECKING:
    from collections.abc import Mapping

    from odoo.orm.models import BaseModel
    from odoo.orm.primitives import IdType
    from odoo.orm.runtime import Environment
    from odoo.orm.runtime._model_types import (
        AuthUserClientModel,
        DecimalPrecisionModel,
        IrAccessLogModel,
        IrAccessModel,
        IrAccessObligationModel,
        IrAttachmentModel,
        IrConfigParameterModel,
        IrCronModel,
        IrDefaultModel,
        IrFieldsConverterModel,
        IrHttpModel,
        IrModelConstraintModel,
        IrModelDataModel,
        IrModelFieldsModel,
        IrModelFieldsSelectionModel,
        IrModelInheritModel,
        IrModelModel,
        IrModelRelationModel,
        IrModuleModuleModel,
        IrQWebModel,
        IrUiViewModel,
        ResCompanyModel,
        ResCountryModel,
        ResCurrencyModel,
        ResGroupsModel,
        ResLangModel,
        ResUsersApikeysScopeModel,
        ResUsersModel,
    )


def model_lookup_contracts(env: Environment, model_name: str) -> None:
    assert_type(env["decimal.precision"], DecimalPrecisionModel)
    assert_type(env["ir.attachment"], IrAttachmentModel)
    assert_type(env["ir.config_parameter"], IrConfigParameterModel)
    assert_type(env["ir.cron"], IrCronModel)
    assert_type(env["ir.http"], IrHttpModel)
    assert_type(env["ir.default"], IrDefaultModel)
    assert_type(env["ir.model"], IrModelModel)
    assert_type(env["ir.access"], IrAccessModel)
    assert_type(env["ir.model.constraint"], IrModelConstraintModel)
    assert_type(env["ir.model.data"], IrModelDataModel)
    assert_type(env["ir.model.fields"], IrModelFieldsModel)
    assert_type(env["ir.model.fields.selection"], IrModelFieldsSelectionModel)
    assert_type(env["ir.model.inherit"], IrModelInheritModel)
    assert_type(env["ir.model.relation"], IrModelRelationModel)
    assert_type(env["ir.module.module"], IrModuleModuleModel)
    assert_type(env["ir.qweb"], IrQWebModel)
    assert_type(env["ir.ui.view"], IrUiViewModel)
    assert_type(env["ir.fields.converter"], IrFieldsConverterModel)
    assert_type(env["res.company"], ResCompanyModel)
    assert_type(env["res.country"], ResCountryModel)
    assert_type(env["res.currency"], ResCurrencyModel)
    assert_type(env["res.lang"], ResLangModel)
    assert_type(env["res.users"], ResUsersModel)
    assert_type(env["auth.user.client"], AuthUserClientModel)
    assert_type(env["res.users.apikeys.scope"], ResUsersApikeysScopeModel)
    assert_type(env["res.groups"], ResGroupsModel)
    assert_type(env["ir.access.log"], IrAccessLogModel)
    assert_type(env["ir.access.obligation"], IrAccessObligationModel)
    assert_type(env[model_name], BaseModel)
    models: Mapping[str, BaseModel] = env
    assert_type(models["res.company"], BaseModel)


def recordset_contracts(env: Environment) -> None:
    companies = env["res.company"]
    model: BaseModel = companies
    assert_type(model, BaseModel)
    assert_type(companies.browse(None), ResCompanyModel)
    assert_type(companies.browse([1, 2]), ResCompanyModel)
    assert_type(companies.sudo().with_context(active_test=False), ResCompanyModel)
    assert_type(companies.search([]), ResCompanyModel)
    assert_type(companies.search_fetch([], ["name"]), ResCompanyModel)
    assert_type(companies.create({"name": "Company"}), ResCompanyModel)
    assert_type(companies.create([{"name": "Company"}]), ResCompanyModel)
    assert_type(companies[0], ResCompanyModel)
    assert_type(companies[:1], ResCompanyModel)
    assert_type(companies.ids, list[int])
    assert_type(companies.id, IdType | bool)
    assert_type(companies._name, str)
    assert_type(companies.check_access("read"), None)
    assert_type(env.user, ResUsersModel)
    assert_type(env.company, ResCompanyModel)
    assert_type(env.companies, ResCompanyModel)
    assert_type(env.user.company_id, ResCompanyModel)
    assert_type(env.user.company_ids, ResCompanyModel)
    assert_type(env.user.login, str | Literal[False])
    assert_type(env.company.sudo().search([]), ResCompanyModel)
    assert_type(env["ir.config_parameter"].init(force=True), None)
    assert_type(env["ir.qweb"]._pregenerate_assets_bundles(), list[str])
    assert_type(env["ir.qweb"]._warm_page_assets(), None)
    companies.browse(1.5)  # type: ignore[arg-type]  # IDs do not accept floating-point scalars.
    companies.search(3)  # type: ignore[arg-type]  # Searches require a domain.
    companies.create(3)  # type: ignore[arg-type]  # Creation requires value mappings.
    env["decimal.precision"].get_precision(3)  # type: ignore[arg-type]  # Retain model-specific parameters.
    env["ir.config_parameter"].init(force="yes")  # type: ignore[arg-type]  # Retain specialized overrides.
