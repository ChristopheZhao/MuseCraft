"""Durable project workspace authority backing for project-mode read/write surfaces."""

from sqlalchemy import Column, JSON, String

from .base import BaseModel


class ProjectWorkspace(BaseModel):
    __tablename__ = "project_workspaces"

    project_id = Column(String(36), unique=True, nullable=False, index=True)
    mode = Column(String(20), nullable=False, default="project")
    payload = Column(JSON, nullable=False, default=dict)
