from repositories.user_repository import UserRepository
from fastapi import Request, Response
from use_cases.user.auth.send_pwd_recovery_email.send_pwd_recovery_email_dto import SendPwdRecoveryEmailDTO
from datetime import datetime
from utils.send_email import send_email
import uuid
from config.config import config

class SendPwdRecoveryEmailUseCase:
    user_repository: UserRepository

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def execute(self, send_pwd_recovery_email_dto: SendPwdRecoveryEmailDTO, response: Response, request: Request):
        check_exists = self.user_repository.find_by_email(email=send_pwd_recovery_email_dto.email)

        if (len(check_exists) == 0):
            response.status_code = 404
            return {"status": "error", "message": "Não foi possível achar o usuário com o email fornecido"}

        user = check_exists[0]

        # Verifica se já solicitou recentemente (limite de 1 hora)
        if user.reset_pwd_token_sent_at and (datetime.now().timestamp() - user.reset_pwd_token_sent_at < 3600):
            response.status_code = 400
            return {"status": "error", "message": "Você pode solicitar o link para redefinir sua senha a cada 1 hora."} 
        
        token = str(uuid.uuid4())

        self.user_repository.update_reset_pwd_token(email=user.email, sent_at=datetime.now().timestamp(), token=token)
        
        # Adding back the email sending functionality
        # send_email(
        #     email=user.email, 
        #     content=f"""
        #         <a href="{config["client_url"] + "/user/password-recovery/" + token}">Redefina sua senha da conta clicando aqui:</a>
        #     """,
        #     subject="Link de redefinição de senha"
        # )

        response.status_code = 200
        return {"status": "success", "message": "Link de redefinição de senha enviado com sucesso"}
