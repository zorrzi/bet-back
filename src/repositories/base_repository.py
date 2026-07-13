from sqlalchemy.orm import Session
from typing import TypeVar, Type, Generic, Dict, Any

T = TypeVar('T')

class BaseRepository(Generic[T]):
    def __init__(self, session: Session, model: Type[T]):
        self.session = session
        self.model = model

    def get_all(self) -> list[T]:
        return self.session.query(self.model).all()

    def add(self, entity: T) -> T:
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def update(self, entity: T) -> T:
        self.session.merge(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity
    
    def update_entity(self, entity: T, update_data: Dict[str, Any]) -> T:
        """Atualiza uma entidade com os dados fornecidos"""
        for key, value in update_data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        self.session.commit()
        self.session.refresh(entity)
        return entity