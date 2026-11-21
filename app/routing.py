from .schemas import IssueCategory, TeamOwner

ROUTES = {
    IssueCategory.ORDER: TeamOwner.FULFILLMENT,
    IssueCategory.PAYMENT: TeamOwner.PAYMENTS,
    IssueCategory.DELIVERY: TeamOwner.LOGISTICS,
    IssueCategory.PRODUCT: TeamOwner.CUSTOMER_SUPPORT,
    IssueCategory.ACCOUNT: TeamOwner.TECH,
    IssueCategory.REFUND: TeamOwner.PAYMENTS,
    IssueCategory.OTHER: TeamOwner.CUSTOMER_SUPPORT,
}

def assign_team(category: IssueCategory) -> TeamOwner:
    return ROUTES[category]
