from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response, status
from starlette.datastructures import UploadFile as StarletteUploadFile

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.catalogue.models import (
    Alias,
    AliasCreate,
    AliasList,
    BaseUnitList,
    ImportCommitRequest,
    ImportKind,
    ImportPreview,
    ImportResult,
    Product,
    ProductCreate,
    ProductList,
    ProductListStatus,
    ProductUpdate,
    SubstituteCreate,
    Supplier,
    SupplierCreate,
    SupplierList,
    SupplierListStatus,
    SupplierUpdate,
)
from procurepilot_api.modules.catalogue.service import CatalogueService, get_catalogue_service

router = APIRouter(tags=["catalogue"])

WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.get("/products", response_model=ProductList)
def list_products(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
    status: Annotated[ProductListStatus, Query()] = "active",
    q: Annotated[str | None, Query()] = None,
) -> ProductList:
    return service.list_products(
        bearer_token=token,
        cursor=cursor,
        limit=limit,
        status=status,
        q=q,
    )


@router.post("/products", status_code=status.HTTP_201_CREATED, response_model=Product)
def create_product(
    payload: Annotated[ProductCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Product:
    return service.create_product(bearer_token=token, member=member, payload=payload)


@router.get("/products/{product_id}", response_model=Product)
def get_product(
    product_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> Product:
    return service.get_product(bearer_token=token, product_id=product_id)


@router.patch("/products/{product_id}", response_model=Product)
def update_product(
    product_id: UUID,
    payload: Annotated[ProductUpdate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> Product:
    return service.update_product(
        bearer_token=token,
        member=member,
        product_id=product_id,
        patch=payload,
    )


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_product(
    product_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> Response:
    service.archive_product(bearer_token=token, member=member, product_id=product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/products/{product_id}/substitutes", status_code=status.HTTP_201_CREATED)
def add_substitute(
    product_id: UUID,
    payload: Annotated[SubstituteCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> Response:
    service.add_substitute(
        bearer_token=token,
        member=member,
        product_id=product_id,
        payload=payload,
    )
    return Response(status_code=status.HTTP_201_CREATED)


@router.get("/reference/base-units", response_model=BaseUnitList)
def list_base_units(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> BaseUnitList:
    return service.list_base_units(bearer_token=token)


@router.get("/suppliers", response_model=SupplierList)
def list_suppliers(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
    status: Annotated[SupplierListStatus, Query()] = "active",
) -> SupplierList:
    return service.list_suppliers(
        bearer_token=token,
        cursor=cursor,
        limit=limit,
        status=status,
    )


@router.post("/suppliers", status_code=status.HTTP_201_CREATED, response_model=Supplier)
def create_supplier(
    payload: Annotated[SupplierCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Supplier:
    return service.create_supplier(bearer_token=token, member=member, payload=payload)


@router.get("/suppliers/{supplier_id}", response_model=Supplier)
def get_supplier(
    supplier_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> Supplier:
    return service.get_supplier(bearer_token=token, supplier_id=supplier_id)


@router.patch("/suppliers/{supplier_id}", response_model=Supplier)
def update_supplier(
    supplier_id: UUID,
    payload: Annotated[SupplierUpdate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> Supplier:
    return service.update_supplier(
        bearer_token=token,
        member=member,
        supplier_id=supplier_id,
        patch=payload,
    )


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_supplier(
    supplier_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> Response:
    service.archive_supplier(bearer_token=token, member=member, supplier_id=supplier_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/aliases", response_model=AliasList)
def list_aliases(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> AliasList:
    return service.list_aliases(bearer_token=token)


@router.post("/aliases", status_code=status.HTTP_201_CREATED, response_model=Alias)
def create_alias(
    payload: Annotated[AliasCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> Alias:
    return service.create_alias(bearer_token=token, member=member, payload=payload)


@router.delete("/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_alias(
    alias_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> Response:
    service.remove_alias(bearer_token=token, member=member, alias_id=alias_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/imports", response_model=ImportPreview)
async def preview_import(
    request: Request,
    _token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> ImportPreview:
    form = await request.form()
    kind = _import_kind(form.get("kind"))
    file = form.get("file")
    if not isinstance(file, StarletteUploadFile):
        raise UnprocessableEntityError(details={"file": "required"})
    content = await file.read()
    if not isinstance(content, bytes):
        raise UnprocessableEntityError(details={"file": "invalid"})
    filename = str(file.filename or "")
    content_type = file.content_type
    return service.preview_import(
        member=member,
        kind=kind,
        filename=filename,
        content=content,
        content_type=str(content_type) if content_type else None,
    )


@router.post("/imports/{import_id}/commit", response_model=ImportResult)
def commit_import_job(
    import_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
    payload: Annotated[ImportCommitRequest | None, Body()] = None,
) -> ImportResult:
    return service.commit_import_job(
        bearer_token=token,
        member=member,
        import_id=import_id,
        on_duplicate=(payload.on_duplicate if payload is not None else "skip"),
    )


def _import_kind(value: object) -> ImportKind:
    if value in {"products", "suppliers"}:
        return value
    raise UnprocessableEntityError(details={"kind": "must_be_products_or_suppliers"})
