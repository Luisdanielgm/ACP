from __future__ import annotations

from pydantic import BaseModel, Field

VALID_ROLES = {"instance_admin", "workspace_admin", "workspace_member"}
VALID_STATUSES = {"active", "disabled"}


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class CreateWorkspaceRequest(BaseModel):
    slug: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=128)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")
    admin_email: str | None = Field(default=None, max_length=254)


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")


class CreateWorkspaceAdminInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class CreateWorkspaceSessionRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str | None = Field(default=None, max_length=160)
    project: str | None = Field(default=None, max_length=160)
    prompt: str | None = Field(default=None, max_length=4000)
    capabilities: list[str] | None = None


class CreateAgentTokenRequest(BaseModel):
    label: str | None = Field(default=None, max_length=64)
    agent_name: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")


class CreateWorkspacePresetRequest(BaseModel):
    preset_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")


class JoinWorkspaceSessionRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    capabilities: list[str] | None = None


class CloseWorkspaceSessionRequest(BaseModel):
    detail: str | None = Field(default=None, max_length=240)


class CreateRoomWallPostRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    pinned: bool = False


class CreateAgentRoomWallPostRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    body: str = Field(min_length=1, max_length=4000)


class UpdateRoomWallPostRequest(BaseModel):
    pinned: bool


class AcceptWorkspaceInvitationRequest(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)


WORKSPACE_TEAM_PRESETS: dict[str, dict[str, object]] = {
    "chief-reviewer": {
        "title": "Chief + Reviewer",
        "body": "Un agente principal abre la sesion y un segundo agente entra para revisar, contrastar o cerrar tareas.",
        "agents": ("codex-chief", "claude-review"),
    },
    "chief-implementer": {
        "title": "Chief + Implementer",
        "body": "Un agente principal coordina y el segundo agente se enfoca en ejecutar cambios o resolver una parte concreta.",
        "agents": ("codex-chief", "claude-implementer"),
    },
}
