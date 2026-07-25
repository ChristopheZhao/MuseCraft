"""Durable project workspace authority backing for project-mode read/write surfaces."""

from sqlalchemy import Column, Integer, JSON, String

from .base import BaseModel


class ProjectWorkspace(BaseModel):
    __tablename__ = "project_workspaces"

    project_id = Column(String(36), unique=True, nullable=False, index=True)
    mode = Column(String(20), nullable=False, default="project")
    version = Column(Integer, nullable=False, default=1)
    payload = Column(JSON, nullable=False, default=dict)
