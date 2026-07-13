from repositories.user_repository import UserRepository
from fastapi import Request, Response, Depends
from use_cases.user.auth.reset_pwd.reset_pwd_use_case import ResetPwdUseCase
from use_cases.user.auth.reset_pwd.reset_pwd_dto import ResetPwdDTO
from fastapi import APIRouter
from sqlalchemy.orm import Session
from database.database import get_db

router = APIRouter()

@router.post("/user/auth/reset/pwd")
def reset_pwd(reset_pwd_dto: ResetPwdDTO, response: Response, request: Request, db: Session = Depends(get_db)):
    user_repository = UserRepository(db)
    reset_pwd_use_case = ResetPwdUseCase(user_repository)
    return reset_pwd_use_case.execute(reset_pwd_dto, response, request)

    