from pydantic import BaseModel
from typing import Optional


class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = "default_session"


class QuestionResponse(BaseModel):
    answer: str
    success: bool
    error_message: Optional[str] = None
    session_id: str

