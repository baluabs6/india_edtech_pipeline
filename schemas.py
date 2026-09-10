from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class TokenRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=128)
    client_secret: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=10)
    language: Optional[str] = Field(default=None, min_length=2, max_length=5)

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question cannot be blank")
        return v


class AskFeedbackRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: Optional[str] = Field(default=None, max_length=8000)
    rating: Literal["up", "down"]
    comment: str = Field(default="", max_length=1000)


class StudentsAtRiskQuery(BaseModel):
    limit: int = Field(default=10, ge=1, le=500)
