from repositories.user_repository import UserRepository
from use_cases.user.auth.register.register_dto import RegisterDTO
from fastapi import Request, Response
from entities.user import User

class RegisterUseCase:
    user_repository: UserRepository

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def execute(self, register_dto: RegisterDTO, response: Response, request: Request):
        if not register_dto.name or not register_dto.email or not register_dto.password:
            response.status_code = 406
            return {"status": "error", "message": "Cadastro não realizado, pois falta informações"}

        # Verifica se o email já existe
        existing_user = self.user_repository.find_by_email(register_dto.email)
        if existing_user:
            response.status_code = 409
            return {"status": "error", "message": "Email já cadastrado"}

        user = User(**register_dto.model_dump())

        self.user_repository.save(user)

        response.status_code = 201

        return {"status": "success", "message": "Cadastro do usuário realizado com sucesso"}
