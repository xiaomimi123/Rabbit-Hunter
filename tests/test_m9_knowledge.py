"""M9 知识层数据模型测试。"""
import json
import os
import tempfile

import pytest

from scripts.m9_knowledge import (
    add_book,
    add_candidate_rule,
    approve_candidate,
    chunk_text,
    ensure_tables,
    get_approved_rules,
    get_candidate,
    ingest_chunks,
    list_books,
    list_candidates,
    record_validation,
    reject_candidate,
)


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        ensure_tables(path)
        yield path
    finally:
        os.unlink(path)


# ─── chunk_text ───────────────────────────────


def test_chunk_text_empty_returns_empty():
    assert chunk_text("") == []


def test_chunk_text_basic_no_overlap():
    chunks = chunk_text("abcdefghij", chunk_size=4, overlap=0)
    assert chunks == ["abcd", "efgh", "ij"]


def test_chunk_text_with_overlap():
    chunks = chunk_text("abcdefghij", chunk_size=4, overlap=1)
    # step = 3
    assert chunks == ["abcd", "defg", "ghij", "j"]


def test_chunk_text_rejects_bad_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=0)


def test_chunk_text_rejects_overlap_ge_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=4, overlap=4)


# ─── books ───────────────────────────────


def test_add_book_returns_id(db_path):
    bid = add_book(db_path, title="Quantitative Trading", author="Ernest Chan")
    assert bid >= 1


def test_list_books_returns_inserted(db_path):
    bid = add_book(db_path, title="Quant Trading", source_type="pdf",
                   content_text="hello world")
    books = list_books(db_path)
    assert len(books) == 1
    assert books[0]["id"] == bid
    assert books[0]["title"] == "Quant Trading"
    assert books[0]["content_length"] == len("hello world")
    assert books[0]["n_candidates"] == 0


def test_ingest_chunks_splits_content(db_path):
    bid = add_book(db_path, title="X", content_text="a" * 2500)
    n = ingest_chunks(db_path, bid, chunk_size=1000, overlap=100)
    # 2500 chars, step=900, chunks at [0:1000], [900:1900], [1800:2500] = 3 chunks
    assert n == 3


def test_ingest_chunks_no_content_no_chunks(db_path):
    bid = add_book(db_path, title="X", content_text=None)
    assert ingest_chunks(db_path, bid) == 0


# ─── candidates ───────────────────────────────


def test_add_candidate_default_status_pending(db_path):
    cid = add_candidate_rule(
        db_path, name="DBL bottom long",
        rule_spec={"setup_type_name": "price_action_double_bottom_long",
                   "side": "LONG", "indicator_overrides": {}},
    )
    c = get_candidate(db_path, cid)
    assert c is not None
    assert c["status"] == "pending"
    assert c["extracted_by"] == "manual"
    spec = json.loads(c["rule_spec_json"])
    assert spec["side"] == "LONG"


def test_list_candidates_filter_by_status(db_path):
    add_candidate_rule(db_path, name="a", rule_spec={"setup_type_name": "a"})
    cid_b = add_candidate_rule(db_path, name="b", rule_spec={"setup_type_name": "b"})
    record_validation(db_path, cid_b, wf_report_path="rep.json", kpi_passes=True)
    pending = list_candidates(db_path, status="pending")
    validated = list_candidates(db_path, status="validated")
    assert len(pending) == 1
    assert len(validated) == 1
    assert validated[0]["wf_report_path"] == "rep.json"
    assert validated[0]["kpi_passes"] == 1


def test_record_validation_sets_path_and_flag(db_path):
    cid = add_candidate_rule(db_path, name="x", rule_spec={})
    record_validation(db_path, cid, wf_report_path="wf.json", kpi_passes=True)
    c = get_candidate(db_path, cid)
    assert c["status"] == "validated"
    assert c["wf_report_path"] == "wf.json"
    assert c["kpi_passes"] == 1
    assert c["validated_at"] is not None


def test_approve_requires_kpi_pass(db_path):
    cid = add_candidate_rule(db_path, name="x", rule_spec={})
    record_validation(db_path, cid, wf_report_path="wf.json", kpi_passes=False)
    with pytest.raises(ValueError, match="未通过 WF KPI"):
        approve_candidate(db_path, cid, approver="lz")


def test_approve_succeeds_when_kpi_passes(db_path):
    cid = add_candidate_rule(db_path, name="x", rule_spec={})
    record_validation(db_path, cid, wf_report_path="wf.json", kpi_passes=True)
    approve_candidate(db_path, cid, approver="lz")
    c = get_candidate(db_path, cid)
    assert c["status"] == "approved"
    assert c["approved_by"] == "lz"
    assert c["approved_at"] is not None


def test_reject_sets_reason(db_path):
    cid = add_candidate_rule(db_path, name="bad rule", rule_spec={})
    reject_candidate(db_path, cid, reason="overfit suspected")
    c = get_candidate(db_path, cid)
    assert c["status"] == "rejected"
    assert c["reject_reason"] == "overfit suspected"


def test_get_approved_rules_only_returns_approved(db_path):
    cid_a = add_candidate_rule(db_path, name="a", rule_spec={})
    cid_b = add_candidate_rule(db_path, name="b", rule_spec={})
    cid_c = add_candidate_rule(db_path, name="c", rule_spec={})
    record_validation(db_path, cid_a, wf_report_path="r.json", kpi_passes=True)
    approve_candidate(db_path, cid_a, approver="lz")
    reject_candidate(db_path, cid_b, reason="x")
    # cid_c 留 pending

    approved = get_approved_rules(db_path)
    assert len(approved) == 1
    assert approved[0]["id"] == cid_a


def test_book_n_candidates_count(db_path):
    """list_books 返回每本书关联的候选规则数。"""
    bid = add_book(db_path, title="X")
    add_candidate_rule(db_path, name="a", rule_spec={}, book_id=bid)
    add_candidate_rule(db_path, name="b", rule_spec={}, book_id=bid)
    add_candidate_rule(db_path, name="c", rule_spec={})  # 独立提案
    books = list_books(db_path)
    assert books[0]["n_candidates"] == 2
