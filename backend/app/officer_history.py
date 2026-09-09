# backend/app/officer_history.py
"""
Officer History API router.

Endpoints:
    POST /api/officer-history   — log an action
    GET  /api/officer-history   — retrieve paginated history

Officer identity strategy
─────────────────────────
Real auth (Task 01) is not yet merged into this branch.
The officer_id is resolved via the following waterfall:

  1. (Future) Bearer token / session cookie set by Task 01 auth middleware.
  2. The X-Officer-ID request header — frontend sends this as the
     logged-in email from ROLE_CONFIG (e.g. 'officer@nic.in').
  3. MOCK_OFFICER_ID fallback — used for local testing with no header.

# TODO: Wire up to real auth context once Task 01 merges.
#       Replace _get_officer_id() with a FastAPI Depends() that
#       reads from the JWT / session set by the auth middleware.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.officer_history_store import (
    create_action,
    get_actions_for_officer,
    delete_action,
    clear_actions_for_officer,
)

# ---------------------------------------------------------------------------
# Mock auth — remove / replace once Task 01 auth merges
# ---------------------------------------------------------------------------
# TODO: Wire up to real auth context once Task 01 merges.
MOCK_OFFICER_ID = "user_123"

router = APIRouter(prefix="/api/officer-history", tags=["officer-history"])


def _get_officer_id(x_officer_id: str | None) -> str:
    """
    Resolve the officer identity from the request.

    Priority:
      1. X-Officer-ID header (sent by the frontend after login)
      2. MOCK_OFFICER_ID fallback (local dev / no auth)

    # TODO: Wire up to real auth context once Task 01 merges.
    """
    return x_officer_id.strip() if x_officer_id and x_officer_id.strip() else MOCK_OFFICER_ID


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

ACTION_TYPES = {"approved", "flagged", "requested_fix"}


class LogActionRequest(BaseModel):
    action_type: str = Field(
        ...,
        description="One of: 'approved', 'flagged', 'requested_fix'",
        examples=["approved"],
    )
    related_standard_or_spec: str = Field(
        ...,
        min_length=1,
        description="IS code or tender spec context, e.g. 'IS 10322 — LED Street Light'",
        examples=["IS 10322 — LED Street Lighting Requirements"],
    )
    notes: str | None = Field(
        default=None,
        description="Optional free-text note from the officer",
        examples=["Voltage spec confirmed against BIS lab report dated 2026-09-01"],
    )


class ActionRecord(BaseModel):
    id: str
    officer_id: str
    action_type: str
    related_standard_or_spec: str
    notes: str | None
    timestamp: str


class PaginatedActions(BaseModel):
    items: list[ActionRecord]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ActionRecord,
    status_code=201,
    summary="Log an officer action",
    description=(
        "Records one procurement action by the currently authenticated officer. "
        "The officer identity is derived from the X-Officer-ID header "
        "(or the mock fallback if the header is absent)."
    ),
)
def log_action(
    body: LogActionRequest,
    x_officer_id: Annotated[str | None, Header()] = None,
) -> ActionRecord:
    """
    POST /api/officer-history

    Request body (JSON):
        {
            "action_type":               "approved" | "flagged" | "requested_fix",
            "related_standard_or_spec":  "IS 10322 — LED Street Light",
            "notes":                     "Optional free text"   (nullable)
        }

    Response (201 Created):
        The persisted action record including its generated id and timestamp.
    """
    officer_id = _get_officer_id(x_officer_id)

    # Validate action_type against the known enum
    if body.action_type not in ACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid action_type '{body.action_type}'. "
                f"Must be one of: {sorted(ACTION_TYPES)}"
            ),
        )

    record = create_action(
        officer_id=officer_id,
        action_type=body.action_type,
        related_standard_or_spec=body.related_standard_or_spec,
        notes=body.notes,
    )
    return ActionRecord(**record)


@router.get(
    "",
    response_model=PaginatedActions,
    summary="Get officer action history",
    description=(
        "Returns the paginated action history for the currently authenticated officer, "
        "ordered newest-first."
    ),
)
def get_history(
    x_officer_id: Annotated[str | None, Header()] = None,
    limit:  int = Query(default=10, ge=1,  le=100, description="Max records per page"),
    offset: int = Query(default=0,  ge=0,           description="Number of records to skip"),
) -> PaginatedActions:
    """
    GET /api/officer-history?limit=10&offset=0

    Query params:
        limit   int  (1-100, default 10)
        offset  int  (>= 0,  default 0)

    Response (200 OK):
        {
            "items":  [ ... action records ... ],
            "total":  42,
            "limit":  10,
            "offset": 0
        }
    """
    officer_id = _get_officer_id(x_officer_id)
    result = get_actions_for_officer(
        officer_id=officer_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedActions(**result)


@router.delete(
    "/{action_id}",
    status_code=204,
    summary="Delete one officer action",
    description=(
        "Permanently removes a single action record. "
        "The record must belong to the requesting officer (anti-IDOR check). "
        "Returns 204 No Content on success, 404 if not found or not owned."
    ),
)
def remove_action(
    action_id: str,
    x_officer_id: Annotated[str | None, Header()] = None,
) -> None:
    """
    DELETE /api/officer-history/{action_id}

    Header:
        X-Officer-Id  — officer identity (or mock fallback)

    Responses:
        204  No Content  — deleted successfully
        404  Not Found   — action_id does not exist or belongs to a different officer
    """
    officer_id = _get_officer_id(x_officer_id)
    found = delete_action(action_id=action_id, officer_id=officer_id)
    if not found:
        raise HTTPException(
            status_code=404,
            detail="Action not found or not owned by this officer.",
        )


@router.delete(
    "",
    status_code=200,
    summary="Clear all history for this officer",
    description=(
        "Permanently removes every action record belonging to the requesting officer. "
        "Returns the count of deleted records."
    ),
)
def clear_history(
    x_officer_id: Annotated[str | None, Header()] = None,
) -> dict:
    """
    DELETE /api/officer-history

    Header:
        X-Officer-Id  — officer identity (or mock fallback)

    Response (200 OK):
        {"deleted": <int>}
    """
    officer_id = _get_officer_id(x_officer_id)
    deleted    = clear_actions_for_officer(officer_id=officer_id)
    return {"deleted": deleted}
