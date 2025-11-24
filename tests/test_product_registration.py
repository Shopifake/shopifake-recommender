"""Tests for the product registration endpoint."""

import pytest


@pytest.mark.asyncio
async def test_register_product(client):
    payload = {
        "product_id": "prod-123",
        "site_id": "site-abc",
        "name": "Aurora Horizon Floor Lamp",
        "description": "Demo product",
        "images": ["https://example.com/lamp.jpg"],
        "categories": [
            {
                "id": "cat-1",
                "site_id": "site-abc",
                "name": "Lighting",
            }
        ],
        "sku": "AUR-LGT-001",
        "status": "PUBLISHED",
        "price": 199.99,
        "filters": [
            {
                "id": "filter-1",
                "name": "Finish",
                "value": "Brushed Brass",
            }
        ],
        "metadata": {"color": "gold"},
    }

    response = await client.post("/products/register", json=payload)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["product_id"] == payload["product_id"]


@pytest.mark.asyncio
async def test_duplicate_registration_allowed(client):
    payload = {
        "product_id": "prod-duplicate",
        "site_id": "site-abc",
        "name": "Original",
        "description": None,
        "images": [],
        "categories": [],
        "sku": "SKU-1",
        "status": "PUBLISHED",
        "filters": [],
        "metadata": {},
    }

    first = await client.post("/products/register", json=payload)
    second = await client.post("/products/register", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["product_id"] == payload["product_id"]
    assert second.json()["product_id"] == payload["product_id"]
