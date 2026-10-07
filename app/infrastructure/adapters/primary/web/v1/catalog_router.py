"""Router HTTP del módulo de catálogo (RF-03, RF-04).

Las lecturas de paquetes, temáticas y extras son públicas (las consume también el bot
de WhatsApp) y **no exponen** ``direct_cost``: ese campo solo se devuelve a
``ENCARGADO`` y ``SUPERADMIN``. Los endpoints de escritura exigen uno de esos roles y
la eliminación es siempre baja lógica (``is_active = false``).
"""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query

from app.application.dtos.catalog_dto import (
    InventoryRequirementDTO,
    PackageReadDTO,
    ThemeDTO,
)
from app.application.ports.output.catalog_admin_port import ICatalogAdminPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.use_cases.catalog.manage_catalog import ManageCatalogUseCase
from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.domain.exceptions.resource_exceptions import (
    DuplicateResourceError,
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.catalog_schemas import (
    ExtraListResponse,
    ExtraRequest,
    ExtraResponse,
    InventoryItemListResponse,
    InventoryItemRequest,
    InventoryItemResponse,
    PackageInventoryItemResponse,
    PackageInventoryItemsRequest,
    PackageInventoryItemsResponse,
    PackageListResponse,
    PackageRequest,
    PackageResponse,
    PackageThemesRequest,
    ThemeListResponse,
    ThemeRequest,
    ThemeResponse,
)
from app.infrastructure.di import containers

router = APIRouter(prefix="/catalog", tags=["Catálogo"])

_STAFF = (Role.ENCARGADO, Role.SUPERADMIN)
_BEARER_PREFIX = "Bearer "


async def optional_auth_context(
    settings: Annotated[Settings, Depends(get_settings)],
    users: Annotated[IUserRepositoryPort, Depends(containers.get_user_repository)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext | None:
    """Contexto opcional para los lectores públicos del catálogo.

    Una sesión válida se contrasta con la cuenta vigente: el rol que decide la
    visibilidad de ``direct_cost`` es el actual de la base de datos, no el claim
    del JWT. Sin cabecera, con token inválido o con cuenta inexistente/desactivada
    se atiende como anónimo.
    """
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        return None
    token = authorization[len(_BEARER_PREFIX) :].strip()
    try:
        payload = decode_access_token(token, settings.secret_key)
        user_id = UUID(str(payload["sub"]))
    except Exception:  # noqa: BLE001 - sesión inválida: se atiende como anónimo
        return None
    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        return None
    return AuthContext(user_id=user_id, role=user.role)


def _is_staff(context: AuthContext | None) -> bool:
    return context is not None and context.role in _STAFF


def _theme_response(theme: ThemeDTO) -> ThemeResponse:
    return ThemeResponse.model_validate(theme)


def _package_response(
    package: PackageReadDTO,
    *,
    direct_cost: Decimal | None,
    requirements: tuple[InventoryRequirementDTO, ...],
) -> PackageResponse:
    return PackageResponse(
        id=package.id,
        name=package.name,
        service_category=package.service_category,
        base_price=package.base_price,
        duration_minutes=package.duration_minutes,
        description=package.description,
        is_active=package.is_active,
        direct_cost=direct_cost,
        compatible_themes=[_theme_response(theme) for theme in package.compatible_themes],
        inventory_items=[
            PackageInventoryItemResponse.model_validate(item) for item in requirements
        ],
    )


def _map_validation(exc: ValidationError) -> ProblemError:
    return ProblemError(422, "validation-error", "Error de validación", str(exc))


def _map_not_found(exc: ResourceNotFoundError) -> ProblemError:
    return ProblemError(404, "resource-not-found", "No encontrado", str(exc))


def _map_conflict(exc: ResourceInUseError | DuplicateResourceError) -> ProblemError:
    return ProblemError(409, exc.code, "Conflicto", str(exc))


# ---------------------------------------------------------------------------
# Paquetes
# ---------------------------------------------------------------------------


@router.get("/packages", response_model=PackageListResponse)
async def list_packages(
    context: Annotated[AuthContext | None, Depends(optional_auth_context)],
    catalog: Annotated[ICatalogReadPort, Depends(containers.get_catalog_read_port)],
    admin: Annotated[ICatalogAdminPort, Depends(containers.get_catalog_admin_port)],
    include_inactive: Annotated[bool, Query()] = False,
) -> PackageListResponse:
    staff = _is_staff(context)
    packages = await catalog.list_packages(include_inactive=include_inactive and staff)
    costs = await admin.list_package_direct_costs() if staff else {}
    items = [
        _package_response(
            package,
            direct_cost=costs.get(package.id),
            requirements=(
                tuple(await catalog.get_inventory_requirements(package.id)) if staff else ()
            ),
        )
        for package in packages
    ]
    return PackageListResponse(items=items, total=len(items))


@router.get("/packages/{package_id}", response_model=PackageResponse)
async def get_package(
    package_id: UUID,
    context: Annotated[AuthContext | None, Depends(optional_auth_context)],
    catalog: Annotated[ICatalogReadPort, Depends(containers.get_catalog_read_port)],
    admin: Annotated[ICatalogAdminPort, Depends(containers.get_catalog_admin_port)],
) -> PackageResponse:
    package = await catalog.get_package(package_id)
    if package is None:
        raise ProblemError(404, "resource-not-found", "No encontrado", "Paquete no encontrado")
    staff = _is_staff(context)
    requirements = tuple(await catalog.get_inventory_requirements(package_id)) if staff else ()
    costs = await admin.list_package_direct_costs() if staff else {}
    return _package_response(package, direct_cost=costs.get(package_id), requirements=requirements)


@router.post("/packages", response_model=PackageResponse, status_code=201)
async def create_package(
    payload: Annotated[PackageRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> PackageResponse:
    try:
        result = await use_case.create_package(
            name=payload.name,
            service_category=payload.service_category,
            base_price=payload.base_price,
            direct_cost=payload.direct_cost,
            duration_minutes=payload.duration_minutes,
            description=payload.description,
        )
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    return _package_response(result, direct_cost=payload.direct_cost, requirements=())


@router.patch("/packages/{package_id}", response_model=PackageResponse)
async def update_package(
    package_id: UUID,
    payload: Annotated[PackageRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> PackageResponse:
    try:
        result = await use_case.update_package(
            package_id,
            name=payload.name,
            service_category=payload.service_category,
            base_price=payload.base_price,
            direct_cost=payload.direct_cost,
            duration_minutes=payload.duration_minutes,
            description=payload.description,
        )
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    return _package_response(result, direct_cost=payload.direct_cost, requirements=())


@router.delete("/packages/{package_id}", response_model=PackageResponse)
async def deactivate_package(
    package_id: UUID,
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> PackageResponse:
    try:
        result = await use_case.deactivate_package(package_id)
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    return _package_response(result, direct_cost=None, requirements=())


@router.put("/packages/{package_id}/inventory-items", response_model=PackageInventoryItemsResponse)
async def set_package_inventory_items(
    package_id: UUID,
    payload: Annotated[PackageInventoryItemsRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> PackageInventoryItemsResponse:
    try:
        requirements = await use_case.set_package_inventory_items(
            package_id,
            [(item.inventory_item_id, item.quantity) for item in payload.items],
        )
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    return PackageInventoryItemsResponse(
        package_id=package_id,
        items=[PackageInventoryItemResponse.model_validate(item) for item in requirements],
    )


@router.put("/packages/{package_id}/themes", response_model=ThemeListResponse)
async def set_package_themes(
    package_id: UUID,
    payload: Annotated[PackageThemesRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> ThemeListResponse:
    try:
        themes = await use_case.set_package_themes(package_id, payload.theme_ids)
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    items = [_theme_response(theme) for theme in themes]
    return ThemeListResponse(items=items, total=len(items))


# ---------------------------------------------------------------------------
# Temáticas
# ---------------------------------------------------------------------------


@router.get("/themes", response_model=ThemeListResponse)
async def list_themes(
    catalog: Annotated[ICatalogReadPort, Depends(containers.get_catalog_read_port)],
    include_inactive: Annotated[bool, Query()] = False,
) -> ThemeListResponse:
    themes = await catalog.list_themes(include_inactive=include_inactive)
    items = [_theme_response(theme) for theme in themes]
    return ThemeListResponse(items=items, total=len(items))


@router.post("/themes", response_model=ThemeResponse, status_code=201)
async def create_theme(
    payload: Annotated[ThemeRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> ThemeResponse:
    try:
        result = await use_case.create_theme(name=payload.name, description=payload.description)
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except DuplicateResourceError as exc:
        raise _map_conflict(exc) from exc
    return ThemeResponse.model_validate(result)


@router.patch("/themes/{theme_id}", response_model=ThemeResponse)
async def update_theme(
    theme_id: UUID,
    payload: Annotated[ThemeRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> ThemeResponse:
    try:
        result = await use_case.update_theme(
            theme_id, name=payload.name, description=payload.description
        )
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    except DuplicateResourceError as exc:
        raise _map_conflict(exc) from exc
    return ThemeResponse.model_validate(result)


@router.delete("/themes/{theme_id}", response_model=ThemeResponse)
async def deactivate_theme(
    theme_id: UUID,
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> ThemeResponse:
    try:
        result = await use_case.deactivate_theme(theme_id)
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    return ThemeResponse.model_validate(result)


# ---------------------------------------------------------------------------
# Extras
# ---------------------------------------------------------------------------


@router.get("/extras", response_model=ExtraListResponse)
async def list_extras(
    context: Annotated[AuthContext | None, Depends(optional_auth_context)],
    catalog: Annotated[ICatalogReadPort, Depends(containers.get_catalog_read_port)],
    admin: Annotated[ICatalogAdminPort, Depends(containers.get_catalog_admin_port)],
    include_inactive: Annotated[bool, Query()] = False,
) -> ExtraListResponse:
    staff = _is_staff(context)
    extras = await catalog.list_extras(include_inactive=include_inactive and staff)
    costs = await admin.list_extra_direct_costs() if staff else {}
    items = [
        ExtraResponse(
            id=extra.id,
            name=extra.name,
            sale_price=extra.sale_price,
            description=extra.description,
            is_active=extra.is_active,
            direct_cost=costs.get(extra.id) if staff else None,
        )
        for extra in extras
    ]
    return ExtraListResponse(items=items, total=len(items))


@router.post("/extras", response_model=ExtraResponse, status_code=201)
async def create_extra(
    payload: Annotated[ExtraRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> ExtraResponse:
    try:
        result = await use_case.create_extra(
            name=payload.name,
            sale_price=payload.sale_price,
            direct_cost=payload.direct_cost,
            description=payload.description,
        )
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    return ExtraResponse(
        id=result.id,
        name=result.name,
        sale_price=result.sale_price,
        description=result.description,
        is_active=result.is_active,
        direct_cost=payload.direct_cost,
    )


@router.patch("/extras/{extra_id}", response_model=ExtraResponse)
async def update_extra(
    extra_id: UUID,
    payload: Annotated[ExtraRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> ExtraResponse:
    try:
        result = await use_case.update_extra(
            extra_id,
            name=payload.name,
            sale_price=payload.sale_price,
            direct_cost=payload.direct_cost,
            description=payload.description,
        )
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    return ExtraResponse(
        id=result.id,
        name=result.name,
        sale_price=result.sale_price,
        description=result.description,
        is_active=result.is_active,
        direct_cost=payload.direct_cost,
    )


@router.delete("/extras/{extra_id}", response_model=ExtraResponse)
async def deactivate_extra(
    extra_id: UUID,
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> ExtraResponse:
    try:
        result = await use_case.deactivate_extra(extra_id)
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    return ExtraResponse(
        id=result.id,
        name=result.name,
        sale_price=result.sale_price,
        description=result.description,
        is_active=result.is_active,
        direct_cost=None,
    )


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------


@router.get("/inventory-items", response_model=InventoryItemListResponse)
async def list_inventory_items(
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    admin: Annotated[ICatalogAdminPort, Depends(containers.get_catalog_admin_port)],
    include_inactive: Annotated[bool, Query()] = False,
) -> InventoryItemListResponse:
    items = [
        InventoryItemResponse.model_validate(item)
        for item in await admin.list_inventory_items(include_inactive=include_inactive)
    ]
    return InventoryItemListResponse(items=items, total=len(items))


@router.post("/inventory-items", response_model=InventoryItemResponse, status_code=201)
async def create_inventory_item(
    payload: Annotated[InventoryItemRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> InventoryItemResponse:
    try:
        result = await use_case.create_inventory_item(
            name=payload.name,
            service_category=payload.service_category,
            total_stock=payload.total_stock,
            description=payload.description,
        )
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except DuplicateResourceError as exc:
        raise _map_conflict(exc) from exc
    return InventoryItemResponse.model_validate(result)


@router.patch("/inventory-items/{item_id}", response_model=InventoryItemResponse)
async def update_inventory_item(
    item_id: UUID,
    payload: Annotated[InventoryItemRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> InventoryItemResponse:
    try:
        result = await use_case.update_inventory_item(
            item_id,
            name=payload.name,
            service_category=payload.service_category,
            total_stock=payload.total_stock,
            description=payload.description,
        )
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    except ResourceInUseError as exc:
        raise _map_conflict(exc) from exc
    except DuplicateResourceError as exc:
        raise _map_conflict(exc) from exc
    return InventoryItemResponse.model_validate(result)


@router.delete("/inventory-items/{item_id}", response_model=InventoryItemResponse)
async def deactivate_inventory_item(
    item_id: UUID,
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCatalogUseCase, Depends(containers.get_manage_catalog_use_case)],
) -> InventoryItemResponse:
    try:
        result = await use_case.deactivate_inventory_item(item_id)
    except ResourceNotFoundError as exc:
        raise _map_not_found(exc) from exc
    except ResourceInUseError as exc:
        raise _map_conflict(exc) from exc
    return InventoryItemResponse.model_validate(result)
