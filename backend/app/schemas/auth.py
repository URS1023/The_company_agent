from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="member", pattern="^(admin|member)$")


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, pattern="^(admin|member)$")
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    status: str
    must_change_password: bool


class LoginResponse(BaseModel):
    user: UserResponse
    workspace_id: str
    requires_password_change: bool


class CreatedUserResponse(BaseModel):
    user: UserResponse
    workspace_id: str
    temporary_password: str


__all__ = [
    "ChangePasswordRequest",
    "CreateUserRequest",
    "CreatedUserResponse",
    "LoginRequest",
    "LoginResponse",
    "UserResponse",
    "UpdateUserRequest",
]
