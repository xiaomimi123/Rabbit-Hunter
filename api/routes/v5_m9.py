"""M9 知识层 + 候选规则审核闸门 API。

依据:文档 §11。所有"非读"操作 (add book / add candidate / validate / approve / reject)
都通过这里走。
"""
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/api/v5/m9", tags=["m9-knowledge"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _reports_dir() -> str:
    return os.environ.get("WF_REPORTS_DIR", "reports")


# ─── Schemas ───────────────────────────────


class BookCreate(BaseModel):
    title: str
    author: Optional[str] = None
    source_type: str = "manual"
    content_text: Optional[str] = None
    notes: Optional[str] = None


class BookOut(BaseModel):
    id: int
    title: str
    author: Optional[str]
    source_type: str
    content_length: Optional[int]
    notes: Optional[str]
    uploaded_at: str
    n_candidates: int


class BooksListResponse(BaseModel):
    books: List[BookOut]


class CandidateCreate(BaseModel):
    name: str
    rule_spec: dict
    book_id: Optional[int] = None
    description: Optional[str] = None
    source_quote: Optional[str] = None
    extracted_by: str = "manual"


class CandidateOut(BaseModel):
    id: int
    book_id: Optional[int]
    name: str
    description: Optional[str]
    rule_spec_json: str
    source_quote: Optional[str]
    extracted_by: str
    status: str
    wf_report_path: Optional[str]
    kpi_passes: Optional[int]
    reject_reason: Optional[str]
    created_at: str
    validated_at: Optional[str]
    approved_at: Optional[str]
    approved_by: Optional[str]


class CandidatesListResponse(BaseModel):
    candidates: List[CandidateOut]


class ValidationRequest(BaseModel):
    start_iso: str
    end_iso: str
    symbols: List[str]
    train_days: int = 30
    oos_days: int = 14
    step_days: int = 14


class ValidationResult(BaseModel):
    wf_report_path: str
    kpi_passes: bool
    n_oos_trades: int
    net_avg_r: float
    net_profit_factor: Optional[float]


class ApproveRequest(BaseModel):
    approver: str = "user"


class RejectRequest(BaseModel):
    reason: str


# ─── Books ───────────────────────────────


@router.post("/books", response_model=BookOut)
async def create_book(payload: BookCreate) -> BookOut:
    from scripts.m9_knowledge import add_book, ingest_chunks, list_books

    bid = add_book(
        _db(),
        title=payload.title, author=payload.author,
        source_type=payload.source_type,
        content_text=payload.content_text, notes=payload.notes,
    )
    # 若有内容,自动切块
    if payload.content_text:
        try:
            ingest_chunks(_db(), bid)
        except Exception as e:
            print(f"[M9] chunk 失败 book={bid}: {e}")

    books = list_books(_db())
    for b in books:
        if b["id"] == bid:
            return BookOut(**b)
    raise HTTPException(500, "book inserted but not found")


@router.get("/books", response_model=BooksListResponse)
async def list_all_books() -> BooksListResponse:
    from scripts.m9_knowledge import list_books
    return BooksListResponse(books=[BookOut(**b) for b in list_books(_db())])


# ─── Candidates ───────────────────────────────


@router.post("/candidates", response_model=CandidateOut)
async def create_candidate(payload: CandidateCreate) -> CandidateOut:
    from scripts.m9_knowledge import add_candidate_rule, get_candidate
    cid = add_candidate_rule(
        _db(),
        name=payload.name, rule_spec=payload.rule_spec,
        book_id=payload.book_id, description=payload.description,
        source_quote=payload.source_quote, extracted_by=payload.extracted_by,
    )
    c = get_candidate(_db(), cid)
    if not c:
        raise HTTPException(500, "candidate inserted but not found")
    return CandidateOut(**c)


@router.get("/candidates", response_model=CandidatesListResponse)
async def list_all_candidates(status: Optional[str] = None) -> CandidatesListResponse:
    from scripts.m9_knowledge import list_candidates
    rows = list_candidates(_db(), status=status)
    return CandidatesListResponse(candidates=[CandidateOut(**c) for c in rows])


@router.post("/candidates/{candidate_id}/validate", response_model=ValidationResult)
async def validate_candidate(
    candidate_id: int, payload: ValidationRequest,
) -> ValidationResult:
    from scripts.m9_validate import trigger_validation
    try:
        result = trigger_validation(
            db_path=_db(), candidate_id=candidate_id,
            start_iso=payload.start_iso, end_iso=payload.end_iso,
            symbols=payload.symbols,
            train_days=payload.train_days, oos_days=payload.oos_days,
            step_days=payload.step_days,
            reports_dir=_reports_dir(),
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"validation failed: {e}")
    return ValidationResult(**result)


@router.post("/candidates/{candidate_id}/approve")
async def approve(candidate_id: int, payload: ApproveRequest):
    from scripts.m9_knowledge import approve_candidate
    try:
        approve_candidate(_db(), candidate_id, approver=payload.approver)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/candidates/{candidate_id}/reject")
async def reject(candidate_id: int, payload: RejectRequest):
    from scripts.m9_knowledge import reject_candidate
    try:
        reject_candidate(_db(), candidate_id, reason=payload.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
