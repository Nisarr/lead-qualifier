"""Integration tests for the lead qualification pipeline.

These tests require the server to be running:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Run with:
    python -m pytest tests/ -v -s
"""

import httpx
import pytest

BASE_URL = "http://localhost:8000"
ENDPOINT = f"{BASE_URL}/webhook/lead"


# ── Test 1: Happy Path ────────────────────────────────────────────────

def test_happy_path_high_intent_lead():
    """A complete, high-intent lead should score Hot or Warm (score > 40)."""
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


# ── Test 2: Missing Message (empty string) ────────────────────────────

def test_missing_message_empty_string():
    """An empty message string should be rejected with status 'rejected'."""
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


# ── Test 3: Missing Message (key omitted entirely) ────────────────────

def test_missing_message_key_omitted():
    """A payload with no 'message' key at all should still be rejected gracefully (not 422)."""
    payload = {
        "full_name": "Alex Rivera",
        "email": "alex@bigco.com",
        "company_name": "BigCo",
        "job_title": "VP Engineering",
    }
    response = httpx.post(ENDPOINT, json=payload, timeout=30.0)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"\n[TEST 3] Response: {data}")
    assert data["status"] == "rejected", f"Expected status='rejected', got: {data['status']}"
    assert data["lead_score"] == 0


# ── Test 4: Low-Context Message ───────────────────────────────────────

def test_low_context_message():
    """A very short message (< 10 chars) should return low_context status."""
    payload = {
        "full_name": "Bob Smith",
        "email": "bob@test.com",
        "company_name": "XYZ Ltd",
        "message": "hi",
    }
    response = httpx.post(ENDPOINT, json=payload, timeout=30.0)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"\n[TEST 4] Response: {data}")
    assert data["status"] == "low_context", f"Expected status='low_context', got: {data['status']}"
    assert data["priority_tier"] == "Cold"
    assert data["lead_score"] == 5


# ── Test 5: Spam Lead ────────────────────────────────────────────────

def test_spam_lead():
    """A spam-like lead should be scored Cold with score < 40."""
    payload = {
        "full_name": "Free Money",
        "email": "promo@spam123.com",
        "company_name": "SEO Guru Agency",
        "message": "We can guarantee you 10x leads for free! Click our link to get started today.",
    }
    response = httpx.post(ENDPOINT, json=payload, timeout=30.0)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"\n[TEST 5] Response: {data}")
    assert data["priority_tier"] == "Cold", f"Expected priority_tier='Cold', got: {data['priority_tier']}"
    assert data["lead_score"] < 40, f"Expected lead_score < 40, got: {data['lead_score']}"


# ── Test 6: Invalid Email Format ──────────────────────────────────────

def test_invalid_email_format():
    """An obviously malformed email should be rejected."""
    payload = {
        "full_name": "Test User",
        "email": "not-an-email",
        "company_name": "Test Co",
        "message": "We need help with automation workflows across our organization.",
    }
    response = httpx.post(ENDPOINT, json=payload, timeout=30.0)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"\n[TEST 6] Response: {data}")
    assert data["status"] == "rejected", f"Expected status='rejected', got: {data['status']}"
    assert "email" in data["next_step"].lower()


# ── Test 7: Missing Full Name ─────────────────────────────────────────

def test_missing_full_name():
    """A payload with an empty full_name should be rejected."""
    payload = {
        "full_name": "",
        "email": "anon@company.com",
        "company_name": "Anon Corp",
        "message": "We need help automating our sales pipeline end to end.",
    }
    response = httpx.post(ENDPOINT, json=payload, timeout=30.0)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"\n[TEST 7] Response: {data}")
    assert data["status"] == "rejected", f"Expected status='rejected', got: {data['status']}"


# ── Test 8: Health Check ──────────────────────────────────────────────

def test_health_endpoint():
    """The /health endpoint should return 200 with status ok."""
    response = httpx.get(f"{BASE_URL}/health", timeout=5.0)
    assert response.status_code == 200
    data = response.json()
    print(f"\n[TEST 8] Response: {data}")
    assert data["status"] == "ok"
