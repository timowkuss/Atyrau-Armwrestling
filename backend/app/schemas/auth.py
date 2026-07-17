from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    full_name: str
    is_active: bool
    role_code: str


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: str
    role_code: str
