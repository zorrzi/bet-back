from pydantic import BaseModel, EmailStr
from typing import Optional
import bcrypt

class User(BaseModel):
    id: Optional[int] = None
    name: str
    email: EmailStr
    password: str
    age: Optional[int] = None
    is_active: bool = True
    reset_pwd_token: Optional[str] = None
    reset_pwd_token_sent_at: Optional[float] = None

    def hash_password(self) -> str:
        """Gera o hash da senha usando bcrypt"""
        return bcrypt.hashpw(self.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password_matches(self, plain_password: str) -> bool:
        """Verifica se a senha fornecida corresponde ao hash armazenado"""
        return bcrypt.checkpw(plain_password.encode('utf-8'), self.password.encode('utf-8'))
