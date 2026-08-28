from pydantic import BaseModel


class CreateProjectRequest(BaseModel):
    name: str


class RenameProjectRequest(BaseModel):
    name: str


class SendMessageRequest(BaseModel):
    content: str


class ReplyRequest(BaseModel):
    content: str
