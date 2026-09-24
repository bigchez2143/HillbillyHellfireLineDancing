"""Local SQLite step catalog.

The JSON glossary remains the easy-to-review source file.  This module builds
``data/line-dance.db`` as the application database: it gives the catalog stable
IDs, queryable tempo fields, and a deliberately review-gated transition table.
It does not invent thousands of unverified transitions from prose descriptions.
"""
import json
import os
import re
import sqlite3


APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(APP_DIR)
SOURCE_PATH = os.path.join(ROOT_DIR, "data", "step-database.json")
from .paths import runtime_path
DATABASE_PATH = runtime_path('line-dance.db', os.path.join(ROOT_DIR, "data", "line-dance.db"))
SCHEMA_VERSION = "1"


def _slug(value):
    value = re.sub(r"[^a-z0-9]+", "-", (value or "step").lower()).strip("-")
    return value or "step"


def _tempo_profile(step):
    """Derive conservative defaults that curators can later override in SQL.

    The glossary was written for dancers, so not every record includes the
    generation-specific tempo fields.  This makes every catalog row queryable
    today without pretending the derived values are choreography certification.
    """
    rotation = abs(int(step.get("net_rotation_deg") or 0))
    travel = (step.get("travels") or "").lower()
    level = (step.get("level") or "").lower()
    preferred_max, penalty = 132, 0.0
    if travel and travel not in ("none", "in place", "on the spot"):
        preferred_max, penalty = min(preferred_max, 128), penalty + 0.8
    if rotation:
        preferred_max, penalty = min(preferred_max, 126), penalty + 1.2
    if "intermediate" in level or "advanced" in level:
        preferred_max, penalty = min(preferred_max, 124), penalty + 0.8
    if int(step.get("counts") or 0) >= 8:
        penalty += 0.3
    return 70, 96, preferred_max, 132, round(penalty, 2)


def initialize_database(database_path=DATABASE_PATH, source_path=SOURCE_PATH):
    """Create or refresh the SQLite catalog from the reviewed JSON source."""
    with open(source_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    source_steps = payload.get("steps", [])
    if not isinstance(source_steps, list):
        raise ValueError("Step database source must contain a 'steps' array.")

    os.makedirs(os.path.dirname(database_path), exist_ok=True)
    con = sqlite3.connect(database_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS steps (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                level TEXT,
                counts INTEGER,
                net_rotation_deg INTEGER,
                travels TEXT,
                foot_start TEXT,
                foot_end TEXT,
                weight_changes INTEGER,
                ab_safe INTEGER NOT NULL DEFAULT 0,
                mirrorable INTEGER NOT NULL DEFAULT 0,
                source TEXT,
                minimum_bpm INTEGER NOT NULL,
                preferred_bpm_min INTEGER NOT NULL,
                preferred_bpm_max INTEGER NOT NULL,
                maximum_bpm INTEGER NOT NULL,
                high_tempo_penalty REAL NOT NULL,
                record_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transitions (
                from_step_id TEXT NOT NULL REFERENCES steps(id),
                to_step_id TEXT NOT NULL REFERENCES steps(id),
                minimum_bpm INTEGER,
                maximum_bpm INTEGER,
                compatibility_score REAL NOT NULL,
                high_tempo_compatibility_score REAL,
                review_status TEXT NOT NULL DEFAULT 'pending',
                notes TEXT,
                PRIMARY KEY (from_step_id, to_step_id)
            );
            CREATE INDEX IF NOT EXISTS idx_steps_level ON steps(level);
            CREATE INDEX IF NOT EXISTS idx_steps_tempo ON steps(maximum_bpm, preferred_bpm_max);
            CREATE INDEX IF NOT EXISTS idx_transitions_review ON transitions(review_status);
        """)

        used_ids = set()
        rows = []
        for step in source_steps:
            base, suffix = _slug(step.get("name")), 2
            step_id = base
            while step_id in used_ids:
                step_id = f"{base}-{suffix}"
                suffix += 1
            used_ids.add(step_id)
            min_bpm, pref_min, pref_max, max_bpm, penalty = _tempo_profile(step)
            rows.append((
                step_id, step.get("name", "Unnamed step"), step.get("category"),
                step.get("level"), step.get("counts"), step.get("net_rotation_deg"),
                step.get("travels"), step.get("foot_start"), step.get("foot_end"),
                step.get("weight_changes"), int(bool(step.get("ab_safe"))),
                int(bool(step.get("mirrorable"))), step.get("source"), min_bpm,
                pref_min, pref_max, max_bpm, penalty,
                json.dumps(step, ensure_ascii=False, sort_keys=True),
            ))
        con.executemany("""
            INSERT INTO steps (
                id, name, category, level, counts, net_rotation_deg, travels,
                foot_start, foot_end, weight_changes, ab_safe, mirrorable, source,
                minimum_bpm, preferred_bpm_min, preferred_bpm_max, maximum_bpm,
                high_tempo_penalty, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, category=excluded.category, level=excluded.level,
                counts=excluded.counts, net_rotation_deg=excluded.net_rotation_deg,
                travels=excluded.travels, foot_start=excluded.foot_start,
                foot_end=excluded.foot_end, weight_changes=excluded.weight_changes,
                ab_safe=excluded.ab_safe, mirrorable=excluded.mirrorable,
                source=excluded.source, minimum_bpm=excluded.minimum_bpm,
                preferred_bpm_min=excluded.preferred_bpm_min,
                preferred_bpm_max=excluded.preferred_bpm_max,
                maximum_bpm=excluded.maximum_bpm,
                high_tempo_penalty=excluded.high_tempo_penalty,
                record_json=excluded.record_json
        """, rows)
        con.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (("schema_version", SCHEMA_VERSION),
             ("source_path", os.path.basename(source_path)),
             ("catalog_steps", str(len(rows))),
             ("transition_policy", "Curated only; unreviewed pairs are not generated.")),
        )
        con.commit()
    finally:
        con.close()
    return database_summary(database_path)


def database_summary(database_path=DATABASE_PATH):
    """Return a small, API-safe inventory of the local choreography data."""
    con = sqlite3.connect(database_path)
    try:
        values = dict(con.execute("SELECT key, value FROM metadata"))
        steps = con.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
        transitions = con.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]
        approved = con.execute(
            "SELECT COUNT(*) FROM transitions WHERE review_status = 'approved'").fetchone()[0]
        return {"path": database_path, "schema_version": values.get("schema_version"),
                "steps": steps, "transitions": transitions,
                "approved_transitions": approved,
                "transition_policy": values.get("transition_policy")}
    finally:
        con.close()
