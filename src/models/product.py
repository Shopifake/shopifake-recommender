"""Product domain models and API schemas."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import AnyHttpUrl, BaseModel, Field


class CategoryPayload(BaseModel):
    """Represents a category coming from the catalog service."""

    id: str = Field(..., description="Unique identifier of the category")
    site_id: str = Field(..., description="Site identifier the category belongs to")
    name: str


class FilterPayload(BaseModel):
    """Represents a product filter assignment."""

    id: str = Field(..., description="Unique identifier of the filter definition")
    name: str
    value: str | None = Field(
        None,
        description="Optional value chosen for the filter",
    )


class ProductPayload(BaseModel):
    """Incoming payload sent by the catalog service when a product is registered."""

    product_id: str = Field(..., description="Unique identifier of the product")
    site_id: str = Field(..., description="Site identifier the product belongs to")
    name: str
    description: str | None = None
    images: list[AnyHttpUrl] = Field(default_factory=list)
    categories: list[CategoryPayload] = Field(default_factory=list)
    sku: str
    status: str = Field(..., description="Publication status of the product")
    price: float | None = Field(
        None,
        ge=0,
        description="Optional price for demo purposes",
    )
    filters: list[FilterPayload] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class RegisteredProduct(ProductPayload):
    """Internal representation persisted inside the registry."""

    registered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the product was registered inside the recommender",
    )
