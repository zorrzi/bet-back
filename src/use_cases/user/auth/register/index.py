from use_cases.user.auth.register.register_use_case import RegisterUseCase
from repositories.user_repository import UserRepository
from fastapi import Request, Response, Depends
from use_cases.user.auth.register.register_dto import RegisterDTO
from fastapi import APIRouter
from sqlalchemy.orm import Session
from database.database import get_db

router = APIRouter()

@router.post("/user/auth/register")
def user_register(register_dto: RegisterDTO, response: Response, request: Request, db: Session = Depends(get_db)):
    user_repository = UserRepository(db)
    user_register_use_case = RegisterUseCase(user_repository)
    return user_register_use_case.execute(register_dto, response, request)

    