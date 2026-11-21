
import logging
import sqlite3
import time

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import settings
from .database import TicketStore
from .auth_store import AuthStore
from .security import AuthUser, current_user, issue_token
from .model import get_classifier
from .routing import assign_team
from .schemas import TicketCreate, ReviewDecision, StatusChange
from .workflow import make_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    if not hasattr(app.state, "store"):
        app.state.store = TicketStore()

    if not hasattr(app.state, "graph"):
        app.state.graph = make_graph(get_classifier())

    app.state.auth_store = AuthStore(app.state.store.path)
    yield


app = FastAPI(
    title="Support Ticket Triage v2 (Secure)",
    version="2.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"]
)


def get_store():
    return app.state.store


def get_graph():
    return app.state.graph


def get_auth_store(store: TicketStore = Depends(get_store)):
    existing = getattr(app.state, "auth_store", None)

    if existing is None or existing.path != store.path:
        app.state.auth_store = AuthStore(store.path)

    return app.state.auth_store


def get_authenticated_user(
    principal: AuthUser = Depends(current_user),
    users: AuthStore = Depends(get_auth_store)
):
    record = users.get_user(principal.user_id)

    if not record or not record["active"]:
        raise HTTPException(401, "Account unavailable")

    # Prevent outdated role claims being accepted after a role change.
    if record["role"] != principal.role:
        raise HTTPException(401, "Authentication must be renewed")

    return principal


def require_staff(user: AuthUser = Depends(get_authenticated_user)):
    if user.role not in ("support", "admin"):
        raise HTTPException(403, "Support staff permission required")
    return user


def check_ticket_access(ticket_id, user, users):
    if user.role in ("support", "admin"):
        return

    if not users.is_owner(ticket_id, user.user_id):
        # Do not reveal the existence of another customer's ticket.
        raise HTTPException(404, "ticket not found")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str


@app.get("/")
def ui():
    return FileResponse(
        Path(__file__).resolve().parent.parent
        / "demo_ui" / "index.html"
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "provider": settings.model_provider,
        "mode": "local"
    }


@app.post("/auth/register", status_code=201)
def register(
    body: RegisterRequest,
    users: AuthStore = Depends(get_auth_store)
):
    try:
        # Public registration NEVER accepts a role.
        user = users.create_user(
            body.username,
            body.password,
            role="customer"
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username already registered")

    return user


@app.post("/auth/login")
def login(
    body: LoginRequest,
    users: AuthStore = Depends(get_auth_store)
):
    user = users.authenticate(body.username, body.password)

    if not user:
        raise HTTPException(401, "Invalid credentials")

    token = issue_token(user["id"], user["role"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"]
    }


@app.get("/auth/me")
def me(user: AuthUser = Depends(get_authenticated_user)):
    return user


@app.post("/tickets", status_code=201)
def create_ticket(
    body: TicketCreate,
    store: TicketStore = Depends(get_store),
    graph=Depends(get_graph),
    user: AuthUser = Depends(get_authenticated_user),
    users: AuthStore = Depends(get_auth_store)
):
    start = time.monotonic()

    result = graph.invoke({"raw_ticket": body.ticket_text})
    ticket = store.create(
        result, body.channel, settings.model_provider
    )

    users.link_owner(ticket["id"], user.user_id)

    logger.info(
        "ticket_created id=%s status=%s elapsed_ms=%.1f",
        ticket["id"],
        ticket["status"],
        (time.monotonic() - start) * 1000
    )

    return ticket


@app.get("/tickets")
def list_tickets(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    store: TicketStore = Depends(get_store),
    user: AuthUser = Depends(get_authenticated_user),
    users: AuthStore = Depends(get_auth_store)
):
    if user.role == "customer":
        return users.list_owned(user.user_id, status, limit)

    return store.list(status, limit)


@app.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str,
    store: TicketStore = Depends(get_store),
    user: AuthUser = Depends(get_authenticated_user),
    users: AuthStore = Depends(get_auth_store)
):
    check_ticket_access(ticket_id, user, users)

    record = store.get(ticket_id)

    if record is None:
        raise HTTPException(404, "ticket not found")

    return record


@app.get("/tickets/{ticket_id}/events")
def get_events(
    ticket_id: str,
    store: TicketStore = Depends(get_store),
    user: AuthUser = Depends(get_authenticated_user),
    users: AuthStore = Depends(get_auth_store)
):
    check_ticket_access(ticket_id, user, users)

    if store.get(ticket_id) is None:
        raise HTTPException(404, "ticket not found")

    return store.events(ticket_id)


@app.post("/tickets/{ticket_id}/review")
def review_ticket(
    ticket_id: str,
    body: ReviewDecision,
    store: TicketStore = Depends(get_store),
    user: AuthUser = Depends(require_staff)
):
    try:
        return store.review(
            ticket_id,
            body.issue_category.value,
            body.priority.value,
            assign_team(body.issue_category).value,
            body.note
        )
    except KeyError:
        raise HTTPException(404, "ticket not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/tickets/{ticket_id}/status")
def update_status(
    ticket_id: str,
    body: StatusChange,
    store: TicketStore = Depends(get_store),
    user: AuthUser = Depends(require_staff)
):
    try:
        return store.change_status(
            ticket_id, body.status, body.note
        )
    except KeyError:
        raise HTTPException(404, "ticket not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
