"""version project definitions and remove mixed runtime authority

Revision ID: 20260719_0002
Revises: 20260711_0001
Create Date: 2026-07-19 12:48:48
"""

import sqlalchemy as sa

from alembic import op

revision = "20260719_0002"
down_revision = "20260711_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_workspaces",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "postgresql":
        op.execute(
            """
            UPDATE project_workspaces
            SET payload = (
                payload::jsonb
                - 'episodes_runtime'
                - 'progress'
                - 'total_cost'
                - 'total_tokens'
                - 'completed_episodes'
            )::json
            WHERE payload IS NOT NULL
            """
        )
    elif dialect_name == "sqlite":
        op.execute(
            """
            UPDATE project_workspaces
            SET payload = json_remove(
                payload,
                '$.episodes_runtime',
                '$.progress',
                '$.total_cost',
                '$.total_tokens',
                '$.completed_episodes'
            )
            WHERE payload IS NOT NULL
            """
        )
    else:
        raise RuntimeError(f"unsupported project payload migration dialect: {dialect_name}")
    op.add_column("tasks", sa.Column("project_id", sa.String(length=100), nullable=True))
    op.add_column("tasks", sa.Column("episode_id", sa.String(length=100), nullable=True))
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"], unique=False)
    op.create_index("ix_tasks_episode_id", "tasks", ["episode_id"], unique=False)
    op.execute(
        """
        UPDATE tasks
        SET project_id = input_parameters ->> 'project_id',
            episode_id = input_parameters ->> 'episode_id'
        WHERE input_parameters IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_episode_id", table_name="tasks")
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_column("tasks", "episode_id")
    op.drop_column("tasks", "project_id")
    op.drop_column("project_workspaces", "version")
