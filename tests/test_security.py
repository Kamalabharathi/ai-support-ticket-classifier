
from fastapi.testclient import TestClient

from app.main import app
from app.database import TicketStore
from app.auth_store import AuthStore
from app.workflow import make_graph
from app.security import issue_token
from .test_pipeline import FakeClassifier


def test_authentication_and_ownership(tmp_path):
    app.dependency_overrides.clear()
    app.state.store = TicketStore(tmp_path / "security.db")
    app.state.graph = make_graph(FakeClassifier())

    with TestClient(app) as client:
        # Unauthenticated access denied.
        assert client.get("/tickets").status_code == 401

        # Register two different customers.
        a = client.post("/auth/register", json={
            "username": "customer_a",
            "password": "CustomerPassword123!"
        })
        assert a.status_code == 201, a.text

        b = client.post("/auth/register", json={
            "username": "customer_b",
            "password": "CustomerPassword456!"
        })
        assert b.status_code == 201, b.text

        # Login.
        login_a = client.post("/auth/login", json={
            "username": "customer_a",
            "password": "CustomerPassword123!"
        })
        assert login_a.status_code == 200, login_a.text

        token_a = login_a.json()["access_token"]

        login_b = client.post("/auth/login", json={
            "username": "customer_b",
            "password": "CustomerPassword456!"
        })
        assert login_b.status_code == 200

        token_b = login_b.json()["access_token"]

        headers_a = {"Authorization": "Bearer " + token_a}
        headers_b = {"Authorization": "Bearer " + token_b}

        # Create an owned ticket.
        response = client.post(
            "/tickets",
            json={
                "ticket_text": "My delivery has not arrived."
            },
            headers=headers_a
        )
        assert response.status_code == 201, response.text

        ticket_id = response.json()["id"]

        # Customer A sees their own ticket.
        assert client.get(
            "/tickets/" + ticket_id,
            headers=headers_a
        ).status_code == 200

        # Customer B cannot see it.
        assert client.get(
            "/tickets/" + ticket_id,
            headers=headers_b
        ).status_code == 404

        assert client.get(
            "/tickets/" + ticket_id + "/events",
            headers=headers_b
        ).status_code == 404

        # Customer B does not see A's ticket in list.
        assert client.get(
            "/tickets", headers=headers_b
        ).json() == []

        # Customer cannot update ticket status.
        change = client.post(
            "/tickets/" + ticket_id + "/status",
            json={
                "status": "in_progress",
                "note": "Unauthorized change"
            },
            headers=headers_a
        )
        assert change.status_code == 403

        # Customer cannot review classifications.
        review = client.post(
            "/tickets/" + ticket_id + "/review",
            json={
                "issue_category": "delivery_issue",
                "priority": "high",
                "note": "Unauthorized review"
            },
            headers=headers_a
        )
        assert review.status_code == 403

        # Create trusted support user through server-side store,
        # not through public registration.
        users = AuthStore(app.state.store.path)
        staff = users.create_user(
            "support_agent",
            "SupportPassword123!",
            role="support"
        )

        staff_token = issue_token(
            staff["user_id"], "support"
        )

        staff_headers = {
            "Authorization": "Bearer " + staff_token
        }

        # Support agent can access all tickets.
        assert client.get(
            "/tickets/" + ticket_id,
            headers=staff_headers
        ).status_code == 200

        # Staff may perform a valid status transition.
        changed = client.post(
            "/tickets/" + ticket_id + "/status",
            json={
                "status": "in_progress",
                "note": "Support started investigation"
            },
            headers=staff_headers
        )
        assert changed.status_code == 200
        assert changed.json()["status"] == "in_progress"

        # Invalid credentials rejected.
        wrong = client.post("/auth/login", json={
            "username": "customer_a",
            "password": "WrongPassword123!"
        })
        assert wrong.status_code == 401

        # Tampered token rejected.
        tampered = client.get(
            "/tickets",
            headers={
                "Authorization": "Bearer " + token_a + "x"
            }
        )
        assert tampered.status_code == 401
