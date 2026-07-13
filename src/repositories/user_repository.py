from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.user_model import UserModel
import bcrypt

class UserRepository(BaseRepository[UserModel]):
    def __init__(self, session: Session):
        super().__init__(session, UserModel)
        
    def get_by_email(self, email: str) -> UserModel | None:
        return self.session.query(self.model).filter(self.model.email == email).first()
    
    def find_by_email(self, email: str) -> list[UserModel]:
        """Busca usuários por email (compatibilidade com código antigo)"""
        user = self.get_by_email(email)
        return [user] if user else []
    
    def find_by_reset_pwd_token(self, token: str) -> list[UserModel]:
        """Busca usuários por token de reset de senha"""
        user = self.session.query(self.model).filter(self.model.reset_pwd_token == token).first()
        return [user] if user else []
    
    def save(self, user_entity) -> UserModel:
        """Salva um novo usuário com senha hash"""
        hashed_password = bcrypt.hashpw(user_entity.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        user_model = UserModel(
            name=user_entity.name,
            email=user_entity.email,
            password=hashed_password,
            age=user_entity.age if hasattr(user_entity, 'age') else None,
            is_active=user_entity.is_active if hasattr(user_entity, 'is_active') else True
        )
        
        return self.add(user_model)
    
    def update_pwd(self, user_id: int, new_password: str) -> UserModel:
        """Atualiza a senha do usuário"""
        user = self.session.query(self.model).filter(self.model.id == user_id).first()
        if user:
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            user.password = hashed_password
            self.session.commit()
            self.session.refresh(user)
        return user
    
    def update_reset_pwd_token(self, email: str, sent_at: float, token: str) -> UserModel | None:
        """Atualiza o token de reset de senha e timestamp"""
        user = self.get_by_email(email)
        if user:
            user.reset_pwd_token = token
            user.reset_pwd_token_sent_at = sent_at
            self.session.commit()
            self.session.refresh(user)
        return user
