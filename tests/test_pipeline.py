"""Unit tests for the lead qualification pipeline."""

import httpx
import pytest

BASE_URL = "http://localhost:8000"
ENDPOINT = f"{BASE_URL}/webhook/lead"


def test_happy_path_high_intent_lead():
    """TEST 1 — Happy Path: High-intent lead should be scored Hot or Warm with score > 40."""
    payload = {
        "full_name": "Jordan Ellis",
        "email": "jordan.ellis@examplecorp.com",
        "company_name": "Example Corp",
        "job_title": "Operations Manager",
        "company_size": "11-50",
        "budget_range": "$5k-$15k/mo",
        "message": "We're drowning in manual data entry across three different tools and need to automate onboarding before headcount doubles next quarter.",
    }
    response = httpx.post(ENDPOINT, json=payload, timeout=30.0)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"\n[TEST 1] Response: {data}")
    assert data["priority_tier"] in ["Hot", "Warm"], f"Expected Hot or Warm, got: {data['priority_tier']}"
    assert data["lead_score"] > 40, f"Expected lead_score > 40, got: {data['lead_score']}"


def test_missing_message_field():
    """TEST 2 — Missing/empty message: should be rejected immediately."""
    payload = {
        "full_name": "Jane Doe",
        "email": "jane@company.com",
        "company_name": "Test Co",
        "message": "",
    }
    response = httpx.post(ENDPOINT, json=payload, timeout=30.0)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"\n[TEST 2] Response: {data}")
    assert data["status"] == "rejected", f"Expected status='rejected', got: {data['status']}"


def test_low_context_message():
    """TEST 3 — Low-context message: should return low_context status."""
    payload = {
        "full_name": "Bob Smith",
        "email": "bob@test.com",
        "company_name": "XYZ Ltd",
        "message": "hi",
    }
    response = httpx.post(ENDPOINT, json=payload, timeout=30.0)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"\n[TEST 3] Response: {data}")
    assert data["status"] == "low_context", f"Expected status='low_context', got: {data['status']}"


def test_spam_lead():
    """TEST 4 — Spam lead: should be scored Cold with lead_score < 40."""
    payload = {
        "full_name": "Free Money",
        "email": "promo@spam123.com",
        "company_name": "SEO Guru Agency",
        "message": "We can guarantee you 10x leads for free! Click our link to get started today.",
    }
    response = httpx.post(ENDPOINT, json=payload, timeout=30.0)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"\n[TEST 4] Response: {data}")
    assert data["priority_tier"] == "Cold", f"Expected priority_tier='Cold', got: {data['priority_tier']}"
    assert data["lead_score"] < 40, f"Expected lead_score < 40 (implies red_flags present), got: {data['lead_score']}"
