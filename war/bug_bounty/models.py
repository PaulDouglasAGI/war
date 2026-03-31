"""
Data models and SQLite storage layer for bug bounty automation.
"""

import sqlite3
import json
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, List


DB_PATH = Path.home() / ".bug_bounty" / "bounty.db"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class Status(str, Enum):
    NEW = "new"
    TRIAGING = "triaging"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    BOUNTY_PAID = "bounty_paid"
    CLOSED = "closed"


class VulnType(str, Enum):
    SQLI = "sqli"
    XSS = "xss"
    RCE = "rce"
    SSRF = "ssrf"
    IDOR = "idor"
    AUTH_BYPASS = "auth_bypass"
    INFO_DISCLOSURE = "info_disclosure"
    CSRF = "csrf"
    XXE = "xxe"
    OPEN_REDIRECT = "open_redirect"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    BROKEN_ACCESS = "broken_access"
    MISCONFIG = "misconfig"
    OTHER = "other"


@dataclass
class Researcher:
    handle: str
    email: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    total_earned: float = 0.0
    report_count: int = 0
    accepted_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Report:
    title: str
    description: str
    vulnerability_type: str
    affected_asset: str
    researcher_id: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    severity: str = Severity.MEDIUM.value
    cvss_score: float = 0.0
    status: str = Status.NEW.value
    bounty_amount: float = 0.0
    steps_to_reproduce: str = ""
    impact: str = ""
    attachments: str = ""          # JSON list of file paths/URLs
    notes: str = ""                # Internal team notes
    duplicate_of: Optional[str] = None
    assigned_to: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    resolved_at: Optional[str] = None


@dataclass
class Program:
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    scope: str = ""                # JSON list of in-scope targets
    out_of_scope: str = ""         # JSON list of out-of-scope targets
    bounty_table: str = ""         # JSON: {severity: amount}
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class AuditLog:
    report_id: str
    action: str
    actor: str
    old_value: str = ""
    new_value: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS researchers (
                id TEXT PRIMARY KEY,
                handle TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                total_earned REAL DEFAULT 0.0,
                report_count INTEGER DEFAULT 0,
                accepted_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS programs (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                scope TEXT,
                out_of_scope TEXT,
                bounty_table TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                vulnerability_type TEXT NOT NULL,
                affected_asset TEXT NOT NULL,
                researcher_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                cvss_score REAL DEFAULT 0.0,
                status TEXT NOT NULL,
                bounty_amount REAL DEFAULT 0.0,
                steps_to_reproduce TEXT,
                impact TEXT,
                attachments TEXT,
                notes TEXT,
                duplicate_of TEXT,
                assigned_to TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY (researcher_id) REFERENCES researchers(id)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (report_id) REFERENCES reports(id)
            );
        """)
        self.conn.commit()

    # --- Researcher CRUD ---

    def create_researcher(self, r: Researcher) -> Researcher:
        self.conn.execute(
            "INSERT INTO researchers VALUES (?,?,?,?,?,?,?)",
            (r.id, r.handle, r.email, r.total_earned, r.report_count, r.accepted_count, r.created_at)
        )
        self.conn.commit()
        return r

    def get_researcher(self, researcher_id: str) -> Optional[Researcher]:
        row = self.conn.execute("SELECT * FROM researchers WHERE id=?", (researcher_id,)).fetchone()
        return self._row_to_researcher(row) if row else None

    def get_researcher_by_handle(self, handle: str) -> Optional[Researcher]:
        row = self.conn.execute("SELECT * FROM researchers WHERE handle=?", (handle,)).fetchone()
        return self._row_to_researcher(row) if row else None

    def list_researchers(self) -> List[Researcher]:
        rows = self.conn.execute("SELECT * FROM researchers ORDER BY total_earned DESC").fetchall()
        return [self._row_to_researcher(r) for r in rows]

    def update_researcher(self, r: Researcher):
        self.conn.execute(
            "UPDATE researchers SET handle=?, email=?, total_earned=?, report_count=?, accepted_count=? WHERE id=?",
            (r.handle, r.email, r.total_earned, r.report_count, r.accepted_count, r.id)
        )
        self.conn.commit()

    def _row_to_researcher(self, row) -> Researcher:
        return Researcher(
            id=row["id"], handle=row["handle"], email=row["email"],
            total_earned=row["total_earned"], report_count=row["report_count"],
            accepted_count=row["accepted_count"], created_at=row["created_at"]
        )

    # --- Program CRUD ---

    def create_program(self, p: Program) -> Program:
        self.conn.execute(
            "INSERT INTO programs VALUES (?,?,?,?,?,?,?,?)",
            (p.id, p.name, p.description, p.scope, p.out_of_scope, p.bounty_table, int(p.active), p.created_at)
        )
        self.conn.commit()
        return p

    def get_program(self, name: str) -> Optional[Program]:
        row = self.conn.execute("SELECT * FROM programs WHERE name=? OR id=?", (name, name)).fetchone()
        return self._row_to_program(row) if row else None

    def list_programs(self) -> List[Program]:
        rows = self.conn.execute("SELECT * FROM programs ORDER BY created_at DESC").fetchall()
        return [self._row_to_program(r) for r in rows]

    def update_program(self, p: Program):
        self.conn.execute(
            "UPDATE programs SET name=?, description=?, scope=?, out_of_scope=?, bounty_table=?, active=? WHERE id=?",
            (p.name, p.description, p.scope, p.out_of_scope, p.bounty_table, int(p.active), p.id)
        )
        self.conn.commit()

    def _row_to_program(self, row) -> Program:
        return Program(
            id=row["id"], name=row["name"], description=row["description"],
            scope=row["scope"], out_of_scope=row["out_of_scope"],
            bounty_table=row["bounty_table"], active=bool(row["active"]),
            created_at=row["created_at"]
        )

    # --- Report CRUD ---

    def create_report(self, r: Report) -> Report:
        self.conn.execute(
            "INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r.id, r.title, r.description, r.vulnerability_type, r.affected_asset,
             r.researcher_id, r.severity, r.cvss_score, r.status, r.bounty_amount,
             r.steps_to_reproduce, r.impact, r.attachments, r.notes,
             r.duplicate_of, r.assigned_to, r.created_at, r.updated_at, r.resolved_at)
        )
        self.conn.commit()
        return r

    def get_report(self, report_id: str) -> Optional[Report]:
        row = self.conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return self._row_to_report(row) if row else None

    def list_reports(self, status: str = None, severity: str = None,
                     researcher_id: str = None) -> List[Report]:
        query = "SELECT * FROM reports WHERE 1=1"
        params = []
        if status:
            query += " AND status=?"
            params.append(status)
        if severity:
            query += " AND severity=?"
            params.append(severity)
        if researcher_id:
            query += " AND researcher_id=?"
            params.append(researcher_id)
        query += " ORDER BY created_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_report(r) for r in rows]

    def update_report(self, r: Report):
        r.updated_at = datetime.utcnow().isoformat()
        self.conn.execute(
            """UPDATE reports SET title=?, description=?, vulnerability_type=?, affected_asset=?,
               severity=?, cvss_score=?, status=?, bounty_amount=?, steps_to_reproduce=?,
               impact=?, notes=?, duplicate_of=?, assigned_to=?, updated_at=?, resolved_at=?
               WHERE id=?""",
            (r.title, r.description, r.vulnerability_type, r.affected_asset,
             r.severity, r.cvss_score, r.status, r.bounty_amount,
             r.steps_to_reproduce, r.impact, r.notes, r.duplicate_of,
             r.assigned_to, r.updated_at, r.resolved_at, r.id)
        )
        self.conn.commit()

    def search_reports(self, query: str) -> List[Report]:
        like = f"%{query}%"
        rows = self.conn.execute(
            """SELECT * FROM reports WHERE title LIKE ? OR description LIKE ?
               OR affected_asset LIKE ? ORDER BY created_at DESC""",
            (like, like, like)
        ).fetchall()
        return [self._row_to_report(r) for r in rows]

    def _row_to_report(self, row) -> Report:
        return Report(
            id=row["id"], title=row["title"], description=row["description"],
            vulnerability_type=row["vulnerability_type"], affected_asset=row["affected_asset"],
            researcher_id=row["researcher_id"], severity=row["severity"],
            cvss_score=row["cvss_score"], status=row["status"],
            bounty_amount=row["bounty_amount"], steps_to_reproduce=row["steps_to_reproduce"] or "",
            impact=row["impact"] or "", attachments=row["attachments"] or "",
            notes=row["notes"] or "", duplicate_of=row["duplicate_of"],
            assigned_to=row["assigned_to"], created_at=row["created_at"],
            updated_at=row["updated_at"], resolved_at=row["resolved_at"]
        )

    # --- Audit Log ---

    def log_action(self, entry: AuditLog):
        self.conn.execute(
            "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?)",
            (entry.id, entry.report_id, entry.action, entry.actor,
             entry.old_value, entry.new_value, entry.timestamp)
        )
        self.conn.commit()

    def get_audit_log(self, report_id: str) -> List[AuditLog]:
        rows = self.conn.execute(
            "SELECT * FROM audit_log WHERE report_id=? ORDER BY timestamp ASC",
            (report_id,)
        ).fetchall()
        return [AuditLog(
            id=r["id"], report_id=r["report_id"], action=r["action"],
            actor=r["actor"], old_value=r["old_value"] or "",
            new_value=r["new_value"] or "", timestamp=r["timestamp"]
        ) for r in rows]

    # --- Stats ---

    def get_stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        by_status = {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT status, COUNT(*) FROM reports GROUP BY status"
            ).fetchall()
        }
        by_severity = {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT severity, COUNT(*) FROM reports GROUP BY severity"
            ).fetchall()
        }
        by_type = {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT vulnerability_type, COUNT(*) FROM reports GROUP BY vulnerability_type"
            ).fetchall()
        }
        total_paid = self.conn.execute(
            "SELECT COALESCE(SUM(bounty_amount), 0) FROM reports WHERE status='bounty_paid'"
        ).fetchone()[0]
        researchers = self.conn.execute("SELECT COUNT(*) FROM researchers").fetchone()[0]
        return {
            "total_reports": total,
            "by_status": by_status,
            "by_severity": by_severity,
            "by_type": by_type,
            "total_paid": total_paid,
            "total_researchers": researchers,
        }
