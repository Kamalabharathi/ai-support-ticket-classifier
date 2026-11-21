from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class IssueCategory(str, Enum):
    ORDER = 'order_issue'
    PAYMENT = 'payment_issue'
    DELIVERY = 'delivery_issue'
    PRODUCT = 'product_issue'
    ACCOUNT = 'account_issue'
    REFUND = 'refund_request'
    OTHER = 'other'

class TeamOwner(str, Enum):
    FULFILLMENT = 'fulfillment_team'
    PAYMENTS = 'payments_team'
    LOGISTICS = 'logistics_team'
    CUSTOMER_SUPPORT = 'customer_support'
    TECH = 'tech_team'

class Priority(str, Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'

class Sentiment(str, Enum):
    POSITIVE = 'positive'
    NEUTRAL = 'neutral'
    NEGATIVE = 'negative'
    ANGRY = 'angry'

class ModelClassification(BaseModel):
    model_config = ConfigDict(extra='forbid')
    issue_category: IssueCategory
    priority: Priority
    user_sentiment: Sentiment
    reasoning: str = Field(min_length=3, max_length=300)
    # Uncalibrated self-report from the model, NOT a validated probability.
    confidence_score: float = Field(ge=0, le=1)

class TicketCreate(BaseModel):
    ticket_text: str = Field(min_length=5, max_length=4000)
    channel: Literal['web_form','email'] = 'web_form'

class ReviewDecision(BaseModel):
    issue_category: IssueCategory
    priority: Priority
    note: str = Field(min_length=3, max_length=300)

class StatusChange(BaseModel):
    status: Literal['in_progress', 'resolved']
    note: str = Field(min_length=3, max_length=300)
