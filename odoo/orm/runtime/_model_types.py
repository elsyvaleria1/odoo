from typing import TYPE_CHECKING, Self, override

if TYPE_CHECKING:
    from .._protocols import (
        AuthUserClientProtocol,
        DecimalPrecisionProtocol,
        IrAccessLogProtocol,
        IrAccessObligationProtocol,
        IrAccessProtocol,
        IrAttachmentProtocol,
        IrConfigParameterProtocol,
        IrCronProtocol,
        IrDefaultProtocol,
        IrFieldsConverterProtocol,
        IrHttpProtocol,
        IrModelConstraintProtocol,
        IrModelDataProtocol,
        IrModelFieldsProtocol,
        IrModelFieldsSelectionProtocol,
        IrModelInheritProtocol,
        IrModelProtocol,
        IrModelRelationProtocol,
        IrModuleModuleProtocol,
        IrQWebProtocol,
        IrUiViewProtocol,
        ResCompanyProtocol,
        ResCountryProtocol,
        ResCurrencyProtocol,
        ResGroupsProtocol,
        ResLangProtocol,
        ResUsersApikeysScopeProtocol,
        ResUsersProtocol,
    )
    from .._typing import ValuesType
    from ..models import BaseModel

    class _FrameworkModel(BaseModel):
        # These interfaces describe records obtained from named registry models.
        _name: str

        @override
        def create(self, vals_list: ValuesType | list[ValuesType]) -> Self: ...

    class AuthUserClientModel(_FrameworkModel, AuthUserClientProtocol): ...

    class DecimalPrecisionModel(_FrameworkModel, DecimalPrecisionProtocol): ...

    class IrAccessModel(_FrameworkModel, IrAccessProtocol): ...

    class IrAccessLogModel(_FrameworkModel, IrAccessLogProtocol): ...

    class IrAccessObligationModel(_FrameworkModel, IrAccessObligationProtocol): ...

    class IrAttachmentModel(_FrameworkModel, IrAttachmentProtocol): ...

    class IrConfigParameterModel(_FrameworkModel, IrConfigParameterProtocol):
        @override
        def init(self, force: bool = False) -> None: ...

    class IrCronModel(_FrameworkModel, IrCronProtocol): ...

    class IrDefaultModel(_FrameworkModel, IrDefaultProtocol): ...

    class IrFieldsConverterModel(_FrameworkModel, IrFieldsConverterProtocol): ...

    class IrHttpModel(_FrameworkModel, IrHttpProtocol): ...

    class IrModelModel(_FrameworkModel, IrModelProtocol): ...

    class IrModelConstraintModel(_FrameworkModel, IrModelConstraintProtocol): ...

    class IrModelDataModel(_FrameworkModel, IrModelDataProtocol): ...

    class IrModelFieldsModel(_FrameworkModel, IrModelFieldsProtocol): ...

    class IrModelFieldsSelectionModel(
        _FrameworkModel, IrModelFieldsSelectionProtocol
    ): ...

    class IrModelInheritModel(_FrameworkModel, IrModelInheritProtocol): ...

    class IrModelRelationModel(_FrameworkModel, IrModelRelationProtocol): ...

    class IrModuleModuleModel(_FrameworkModel, IrModuleModuleProtocol): ...

    class IrQWebModel(_FrameworkModel, IrQWebProtocol): ...

    class IrUiViewModel(_FrameworkModel, IrUiViewProtocol): ...

    class ResCompanyModel(_FrameworkModel, ResCompanyProtocol): ...

    class ResCountryModel(_FrameworkModel, ResCountryProtocol): ...

    class ResCurrencyModel(_FrameworkModel, ResCurrencyProtocol): ...

    class ResGroupsModel(_FrameworkModel, ResGroupsProtocol): ...

    class ResLangModel(_FrameworkModel, ResLangProtocol): ...

    class ResUsersModel(_FrameworkModel, ResUsersProtocol):
        company_id: ResCompanyModel
        company_ids: ResCompanyModel

    class ResUsersApikeysScopeModel(_FrameworkModel, ResUsersApikeysScopeProtocol): ...
