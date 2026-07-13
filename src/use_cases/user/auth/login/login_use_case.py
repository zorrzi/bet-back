from repositories.user_repository import UserRepository
from fastapi import Response, Request
from use_cases.user.auth.login.login_dto import LoginDTO
import jwt
import os
import bcrypt

class LoginUseCase:
    user_repository: UserRepository

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def execute(self, login_dto: LoginDTO, response: Response, request: Request):
        check_exists = self.user_repository.find_by_email(email=login_dto.email)

        if (len(check_exists) == 0):
            response.status_code = 404
            return {"status": "error", "message": "Não foi possível achar um usuário com o email fornecido"}

        user = check_exists[0]

        # Verifica se a senha corresponde ao hash
        if not bcrypt.checkpw(login_dto.password.encode('utf-8'), user.password.encode('utf-8')):
            response.status_code = 400
            return {"status": "error", "message": "Senha incorreta, tente novamente mais tarde."}

        token = jwt.encode({"email": user.email, "id": str(user.id)}, os.getenv("USER_JWT_SECRET"), algorithm="HS256")

        response.set_cookie(
            key="user_auth_token",
            value=f"Bearer {token}",
            httponly=True,
            samesite="None",
            secure=True,
            path="/"  
        )
        
        response.status_code = 202
        return {"status": "success", "message": "Acesso permitido"}
