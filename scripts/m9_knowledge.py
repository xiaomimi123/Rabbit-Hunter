"""M9 策略书籍知识层 — 候选规则的人工审核管线。

依据:Rabbit-Hunter 完整开发设计文档 v1.0 §11。

边界(关键):
- 书籍只产出"候选规则",不直接改实盘逻辑。
- 候选规则必须 walk-forward 验证 + 人工审核才能进 M2 setup 列表。
- AI 提取/语义检索是可选加速器,不是 gate — 用户也能手动输入候选规则。

四步管线:
1. 摄取(upload book → 切块 chunks)
2. 候选规则提取(可手动 或 AI 辅助)
3. Walk-forward 验证(用 scripts/walkforward.py)
4. 人工审核闸门(approve / reject)
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


# ─────────────────────────────────────────────────────────────
# DB schema
# ─────────────────────────────────────────────────────────────


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS m9_books (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL,
    author        TEXT,
    source_type   TEXT    NOT NULL,            -- 'pdf' | 'epub' | 'manual'
    content_text  TEXT,                         -- 全文(若上传 PDF 时已抽取)
    notes         TEXT,                         -- 人工备注
    uploaded_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS m9_knowledge_chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id       INTEGER NOT NULL,
    chunk_index   INTEGER NOT NULL,
    text          TEXT    NOT NULL,
    embedding     BLOB,                          -- 留接口,M9.4 接入 embedding 时填
    UNIQUE(book_id, chunk_index),
    FOREIGN KEY(book_id) REFERENCES m9_books(id)
);

CREATE TABLE IF NOT EXISTS m9_candidate_rules (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id            INTEGER,                 -- NULL 表示纯人工提案
    name               TEXT    NOT NULL,
    description        TEXT,
    rule_spec_json     TEXT    NOT NULL,         -- 规则规格(setup_type 派生 + 入场条件)
    source_quote       TEXT,                     -- 书中的原文引用(可选)
    extracted_by       TEXT    NOT NULL DEFAULT 'manual',  -- 'manual' | 'ai_<provider>'
    status             TEXT    NOT NULL DEFAULT 'pending',  -- pending|validated|approved|rejected|broken
    wf_report_path     TEXT,                     -- 验证后的 WF 报告路径
    kpi_passes         INTEGER,                  -- 1=通过文档 §15 KPI #2,0=未通过,NULL=未验证
    reject_reason      TEXT,                     -- 拒绝时的原因
    created_at         TEXT    NOT NULL,
    validated_at       TEXT,
    approved_at        TEXT,
    approved_by        TEXT,                     -- 审核者
    FOREIGN KEY(book_id) REFERENCES m9_books(id)
);
"""


def ensure_tables(db_path: str) -> None:
    """幂等建表。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────


@dataclass
class Book:
    id: Optional[int]
    title: str
    author: Optional[str]
    source_type: str
    content_text: Optional[str]
    notes: Optional[str]
    uploaded_at: str


@dataclass
class CandidateRule:
    id: Optional[int]
    book_id: Optional[int]
    name: str
    description: Optional[str]
    rule_spec_json: str           # JSON-encoded RuleSpec
    source_quote: Optional[str]
    extracted_by: str
    status: str                    # pending|validated|approved|rejected|broken
    wf_report_path: Optional[str]
    kpi_passes: Optional[int]
    reject_reason: Optional[str]
    created_at: str
    validated_at: Optional[str] = None
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None


# rule_spec_json 的内部结构(无强校验,留灵活性给书里的奇思妙想):
# {
#   "setup_type_name": "price_action_double_bottom_long",
#   "entry_conditions": [...],     # human-readable list
#   "indicator_overrides": {"v5_rsi_oversold": 25},  # 可注入到 v5_params 的覆盖
#   "side": "LONG" | "SHORT" | "BOTH",
#   "min_holding_minutes": 60,
#   "max_holding_minutes": 480,
# }


# ─────────────────────────────────────────────────────────────
# Book CRUD
# ─────────────────────────────────────────────────────────────


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_book(
    db_path: str,
    *,
    title: str,
    author: Optional[str] = None,
    source_type: str = "manual",
    content_text: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    """添加书 → 返回 book_id。"""
    ensure_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO m9_books(title, author, source_type, content_text, notes, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, author, source_type, content_text, notes, _utcnow()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_books(db_path: str) -> List[dict]:
    ensure_tables(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, title, author, source_type, "
            "       LENGTH(content_text) as content_length, notes, uploaded_at, "
            "       (SELECT COUNT(*) FROM m9_candidate_rules WHERE book_id = m9_books.id) AS n_candidates "
            "  FROM m9_books ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Chunk ingest(简单等分,留 embedding 接口)
# ─────────────────────────────────────────────────────────────


def chunk_text(text: str, *, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    """简单字符等分,带 overlap。

    后续 M9.4 接 sentence-aware splitter 时此函数会被替换;现在先工作。
    """
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")

    chunks = []
    step = chunk_size - overlap
    i = 0
    while i < len(text):
        chunks.append(text[i: i + chunk_size])
        i += step
    return chunks


def ingest_chunks(db_path: str, book_id: int, *, chunk_size: int = 1000, overlap: int = 100) -> int:
    """对 book.content_text 切块写 knowledge_chunks。返回写入条数。"""
    ensure_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT content_text FROM m9_books WHERE id = ?", (book_id,)
        ).fetchone()
        if not row or not row[0]:
            return 0
        text = row[0]
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        # 重建该书的 chunks(便于重切)
        conn.execute("DELETE FROM m9_knowledge_chunks WHERE book_id = ?", (book_id,))
        for idx, c in enumerate(chunks):
            conn.execute(
                "INSERT INTO m9_knowledge_chunks(book_id, chunk_index, text) VALUES (?, ?, ?)",
                (book_id, idx, c),
            )
        conn.commit()
        return len(chunks)
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Candidate CRUD + lifecycle
# ─────────────────────────────────────────────────────────────


def add_candidate_rule(
    db_path: str,
    *,
    name: str,
    rule_spec: dict,
    book_id: Optional[int] = None,
    description: Optional[str] = None,
    source_quote: Optional[str] = None,
    extracted_by: str = "manual",
) -> int:
    """添加候选规则 → 返回 candidate_id,初始 status='pending'。"""
    ensure_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO m9_candidate_rules(
                book_id, name, description, rule_spec_json, source_quote,
                extracted_by, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (book_id, name, description, json.dumps(rule_spec, ensure_ascii=False),
             source_quote, extracted_by, _utcnow()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_candidates(db_path: str, status: Optional[str] = None) -> List[dict]:
    """列候选规则。status 过滤可选。"""
    ensure_tables(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM m9_candidate_rules WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM m9_candidate_rules ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_candidate(db_path: str, candidate_id: int) -> Optional[dict]:
    ensure_tables(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM m9_candidate_rules WHERE id = ?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def record_validation(
    db_path: str,
    candidate_id: int,
    *,
    wf_report_path: str,
    kpi_passes: bool,
) -> None:
    """标记候选规则已经做完 WF 验证。"""
    ensure_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE m9_candidate_rules SET status='validated', "
            "wf_report_path=?, kpi_passes=?, validated_at=? WHERE id=?",
            (wf_report_path, 1 if kpi_passes else 0, _utcnow(), candidate_id),
        )
        conn.commit()
    finally:
        conn.close()


def approve_candidate(db_path: str, candidate_id: int, *, approver: str) -> None:
    """人工审核通过 → 状态变 approved。"""
    ensure_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT kpi_passes FROM m9_candidate_rules WHERE id = ?", (candidate_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"candidate {candidate_id} not found")
        # 软警告:文档要求 WF KPI PASS 才能批准
        if row[0] != 1:
            raise ValueError(
                f"candidate {candidate_id} 未通过 WF KPI(kpi_passes={row[0]}),"
                f"不应批准 — 文档 §11 第 4 步"
            )
        conn.execute(
            "UPDATE m9_candidate_rules SET status='approved', "
            "approved_at=?, approved_by=? WHERE id=?",
            (_utcnow(), approver, candidate_id),
        )
        conn.commit()
    finally:
        conn.close()


def reject_candidate(db_path: str, candidate_id: int, *, reason: str) -> None:
    """人工拒绝。"""
    ensure_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE m9_candidate_rules SET status='rejected', "
            "reject_reason=?, validated_at=COALESCE(validated_at, ?) WHERE id=?",
            (reason, _utcnow(), candidate_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_approved_rules(db_path: str) -> List[dict]:
    """已批准的候选规则 = 可被 M2 使用的新 setup 草案。"""
    return list_candidates(db_path, status="approved")


__all__ = [
    "ensure_tables",
    "add_book", "list_books",
    "chunk_text", "ingest_chunks",
    "add_candidate_rule", "list_candidates", "get_candidate",
    "record_validation", "approve_candidate", "reject_candidate",
    "get_approved_rules",
]
