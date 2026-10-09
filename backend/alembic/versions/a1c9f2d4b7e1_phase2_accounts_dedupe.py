"""phase 2: bank account type + transaction import dedupe key

Revision ID: a1c9f2d4b7e1
Revises: 8fb483b1168d
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c9f2d4b7e1'
down_revision: Union[str, None] = '8fb483b1168d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACCOUNT_TYPE_VALUES = (
    "bank",
    "checking",
    "savings",
    "cash",
    "credit_card",
    "debit_card",
    "investment",
    "loan",
    "other",
)

# SQLite cannot alter a CHECK constraint, so the accounts table is rebuilt
# with the widened account type list. The rebuild runs with foreign keys
# disabled (via autocommit_block) so child rows in other tables survive.
ACCOUNTS_V2_SQL = """
CREATE TABLE accounts_v2 (
    id INTEGER NOT NULL,
    name VARCHAR(120) NOT NULL,
    type VARCHAR(11) NOT NULL,
    opening_balance DOUBLE DEFAULT '0' NOT NULL,
    current_balance DOUBLE DEFAULT '0' NOT NULL,
    currency VARCHAR(3),
    active BOOLEAN DEFAULT '1' NOT NULL,
    description TEXT,
    import_metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_accounts PRIMARY KEY (id),
    CONSTRAINT uq_accounts_name UNIQUE (name),
    CONSTRAINT ck_accounts_accounttype CHECK (type IN ({values}))
)
""".format(values=", ".join(f"'{value}'" for value in ACCOUNT_TYPE_VALUES))

ACCOUNTS_COLUMNS = (
    "id",
    "name",
    "type",
    "opening_balance",
    "current_balance",
    "currency",
    "active",
    "description",
    "import_metadata",
    "created_at",
    "updated_at",
)


def upgrade() -> None:
    # 1. Content fingerprint / source reference column used to skip duplicate
    #    CSV imports.
    op.execute("ALTER TABLE transactions ADD COLUMN dedupe_key VARCHAR(128)")
    op.create_index(
        op.f("ix_transactions_dedupe_key"), "transactions", ["dedupe_key"], unique=False
    )

    # 2. Rebuild accounts so the type CHECK includes the 'bank' value.
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
        conn.execute(sa.text(ACCOUNTS_V2_SQL))
        conn.execute(
            sa.text(
                "INSERT INTO accounts_v2 ({cols}) SELECT {cols} FROM accounts".format(
                    cols=", ".join(ACCOUNTS_COLUMNS)
                )
            )
        )
        conn.execute(sa.text("DROP TABLE accounts"))
        conn.execute(sa.text("ALTER TABLE accounts_v2 RENAME TO accounts"))
        conn.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    # Rebuild accounts with the original type list (rows whose type is
    # 'bank' would fail the restored CHECK; map them to 'checking').
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
        conn.execute(
            """
            CREATE TABLE accounts_v1 (
                id INTEGER NOT NULL,
                name VARCHAR(120) NOT NULL,
                type VARCHAR(11) NOT NULL,
                opening_balance DOUBLE DEFAULT '0' NOT NULL,
                current_balance DOUBLE DEFAULT '0' NOT NULL,
                currency VARCHAR(3),
                active BOOLEAN DEFAULT '1' NOT NULL,
                description TEXT,
                import_metadata JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                CONSTRAINT pk_accounts PRIMARY KEY (id),
                CONSTRAINT uq_accounts_name UNIQUE (name),
                CONSTRAINT ck_accounts_accounttype CHECK (type IN
                    ('checking', 'savings', 'cash', 'credit_card',
                     'debit_card', 'investment', 'loan', 'other'))
            )
            """
        )
        conn.execute(
            """
            INSERT INTO accounts_v1 (id, name, type, opening_balance,
                current_balance, currency, active, description,
                import_metadata, created_at, updated_at)
            SELECT id, name,
                   CASE WHEN type = 'bank' THEN 'checking' ELSE type END,
                   opening_balance, current_balance, currency, active,
                   description, import_metadata, created_at, updated_at
            FROM accounts
            """
        )
        conn.execute(sa.text("DROP TABLE accounts"))
        conn.execute(sa.text("ALTER TABLE accounts_v1 RENAME TO accounts"))
        conn.execute(sa.text("PRAGMA foreign_keys=ON"))

    op.drop_index(op.f("ix_transactions_dedupe_key"), table_name="transactions")
    op.execute("ALTER TABLE transactions DROP COLUMN dedupe_key")
