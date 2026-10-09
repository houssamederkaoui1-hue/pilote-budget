"""SQLAlchemy models.

Importing this package registers every model on ``Base.metadata`` (required
for migrations and schema creation).
"""

from app.db.base import Base
from app.models.account import Account
from app.models.budget import Budget, BudgetAllocation
from app.models.category import Category
from app.models.debt import Debt
from app.models.goal import Goal
from app.models.profile import Profile
from app.models.recurring import RecurringTransaction
from app.models.transaction import Transaction
from app.models.transfer import Transfer

__all__ = [
    "Account",
    "Base",
    "Budget",
    "BudgetAllocation",
    "Category",
    "Debt",
    "Goal",
    "Profile",
    "RecurringTransaction",
    "Transaction",
    "Transfer",
]
