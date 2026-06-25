"""Persistent vector memory for detecting similar or returning leads.

Uses sentence-transformers to embed lead text and SQLite to store
embeddings.  On each new lead, cosine similarity is checked against
all stored embeddings to surface prior interactions.

The VectorMemory class is implemented as a **singleton** so the
sentence-transformer model (~90 MB) is loaded only once and the SQLite
connection is reused across requests.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from models import NormalizedLead

# ── Constants ──────────────────────────────────────────────────────────

DB_PATH = "lead_memory.db"
MODEL_NAME = "all-MiniLM-L6-v2"       # small, fast, no API key needed
SIMILARITY_THRESHOLD = 0.82           # above this = "similar lead"


class VectorMemory:
    """Embeds lead text and stores/retrieves vectors via SQLite.

    Implemented as a singleton — calling ``VectorMemory()`` always returns
    the same instance so the embedding model is loaded only once.
    """

    _instance: "VectorMemory | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "VectorMemory":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking for thread safety
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        print("[VECTOR_MEMORY] Loading sentence-transformer model (one-time)...")
        self.model = SentenceTransformer(MODEL_NAME)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_embeddings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name    TEXT,
                email_domain    TEXT,
                message_preview TEXT,
                embedding       TEXT,       -- JSON array of floats
                timestamp       TEXT,
                lead_score      INTEGER,
                priority_tier   TEXT
            )
            """
        )
        self.conn.commit()
        self._initialized = True
        print("[VECTOR_MEMORY] Model loaded ✓")

    # ── helpers ────────────────────────────────────────────────────────

    def _build_text(self, lead: NormalizedLead) -> str:
        """Combine the fields the model should reason about."""
        return (
            f"Company: {lead.company_name}. "
            f"Title: {lead.job_title}. "
            f"Message: {lead.message}"
        )

    # ── public API ────────────────────────────────────────────────────

    def find_similar(self, lead: NormalizedLead) -> dict | None:
        """Return match metadata if a sufficiently similar lead exists."""
        text = self._build_text(lead)
        new_embedding = self.model.encode([text])          # shape (1, dim)

        rows = self.conn.execute(
            "SELECT company_name, message_preview, embedding, "
            "       lead_score, priority_tier "
            "FROM lead_embeddings"
        ).fetchall()

        if not rows:
            return None

        stored_embeddings = np.array(
            [json.loads(row["embedding"]) for row in rows]
        )

        scores = cosine_similarity(new_embedding, stored_embeddings)[0]
        best_idx = int(np.argmax(scores))
        best_score = scores[best_idx]

        if best_score >= SIMILARITY_THRESHOLD:
            matched = rows[best_idx]
            return {
                "matched": True,
                "similarity_score": round(float(best_score), 3),
                "company_name": matched["company_name"],
                "prior_tier": matched["priority_tier"],
                "prior_score": matched["lead_score"],
                "message_preview": matched["message_preview"],
            }

        return None

    def store_lead(
        self, lead: NormalizedLead, score: int, tier: str
    ) -> None:
        """Persist a lead embedding for future similarity lookups."""
        try:
            text = self._build_text(lead)
            embedding = self.model.encode([text])[0]

            email_domain = lead.email.split("@")[-1] if "@" in lead.email else ""
            message_preview = lead.message[:100]

            self.conn.execute(
                """
                INSERT INTO lead_embeddings
                    (company_name, email_domain, message_preview,
                     embedding, timestamp, lead_score, priority_tier)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead.company_name,
                    email_domain,
                    message_preview,
                    json.dumps(embedding.tolist()),
                    datetime.now(timezone.utc).isoformat(),
                    score,
                    tier,
                ),
            )
            self.conn.commit()
        except Exception as exc:
            # Never raise — memory storage is best-effort
            print(f"[VECTOR_MEMORY] store_lead failed: {exc}")
