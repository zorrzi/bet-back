from repositories.user_repository import UserRepository
from fastapi import Request, Response
from use_cases.user.auth.reset_pwd.reset_pwd_dto import ResetPwdDTO
from datetime import datetime

class ResetPwdUseCase:
    user_repository: UserRepository

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def execute(self, reset_pwd_dto: ResetPwdDTO, response: Response, request: Request):
        check_exists = self.user_repository.find_by_reset_pwd_token(token=reset_pwd_dto.token)

        if (len(check_exists) == 0):
            response.status_code = 404
            return {"status": "error", "message": "Não foi possível achar o usuário com o token fornecido"}

        user = check_exists[0]

        # Verifica se o token expirou (60 minutos = 3600 segundos)
        if datetime.now().timestamp() - user.reset_pwd_token_sent_at > 3600:
            response.status_code = 400
            return {"status": "error", "message": "O token de redefinição expirou. Por favor, solicite um novo."} 
        
        self.user_repository.update_pwd(user.id, reset_pwd_dto.password)

        self.user_repository.update_reset_pwd_token(email=user.email, sent_at=0, token="")
        
        return {"status": "success", "message": "Senha alterada com sucesso, faça login para poder entrar em sua conta."}
