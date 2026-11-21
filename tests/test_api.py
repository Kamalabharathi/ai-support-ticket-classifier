from fastapi.testclient import TestClient
from app.main import app
from app.database import TicketStore
from app.workflow import make_graph
from .test_pipeline import FakeClassifier


def test_ticket_lifecycle(tmp_path):
    app.state.store = TicketStore(tmp_path / 'test.db')
    app.state.graph = make_graph(FakeClassifier())
    with TestClient(app) as client:
        res = client.post('/tickets', json={'ticket_text': 'alice@example.com: My delivery has not arrived'})
        assert res.status_code == 201, res.text
        ticket = res.json()
        assert ticket['status'] == 'assigned'
        assert 'alice@example.com' not in ticket['redacted_ticket']
        ticket_id = ticket['id']
        assert client.get('/tickets/' + ticket_id).status_code == 200
        assert len(client.get('/tickets').json()) == 1
        bad = client.post('/tickets/' + ticket_id + '/status', json={'status':'resolved','note':'skip step'})
        assert bad.status_code == 409
        res = client.post('/tickets/' + ticket_id + '/status', json={'status':'in_progress','note':'Engineer started investigation'})
        assert res.status_code == 200
        res = client.post('/tickets/' + ticket_id + '/status', json={'status':'resolved','note':'Delivery issue closed'})
        assert res.status_code == 200
        assert len(client.get('/tickets/'+ticket_id+'/events').json()) == 3


def test_pending_review(tmp_path):
    class LowConfidence(FakeClassifier):
        def classify(self, text):
            c = super().classify(text)
            return c.model_copy(update={'confidence_score': 0.3})
    app.state.store = TicketStore(tmp_path / 'review.db')
    app.state.graph = make_graph(LowConfidence())
    with TestClient(app) as client:
        ticket = client.post('/tickets', json={'ticket_text':'My delivery has not arrived'}).json()
        assert ticket['status'] == 'pending_review'
        result = client.post('/tickets/'+ticket['id']+'/review', json={'issue_category':'delivery_issue','priority':'high','note':'Checked by local reviewer'})
        assert result.status_code == 200
        assert result.json()['status'] == 'assigned'


# Existing lifecycle tests use a trusted support principal.
# Dedicated security tests below exercise real JWT authentication.
import pytest
from app.main import get_authenticated_user
from app.security import AuthUser

@pytest.fixture(autouse=True)
def legacy_test_support_identity():
    app.dependency_overrides[get_authenticated_user] = (
        lambda: AuthUser(user_id="legacy-test-support", role="support")
    )
    yield
    app.dependency_overrides.pop(get_authenticated_user, None)

