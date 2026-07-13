# Backend Template - FastAPI + SQLAlchemy

Este é um template de backend desenvolvido com FastAPI e SQLAlchemy, pronto para ser usado como base para projetos que necessitam de autenticação de usuários.

## 🚀 Características

- **FastAPI**: Framework web moderno e rápido
- **SQLAlchemy**: ORM para banco de dados relacional (MySQL)
- **Alembic**: Gerenciamento de migrações de banco de dados
- **Bcrypt**: Hash seguro de senhas
- **JWT**: Autenticação baseada em tokens
- **SendGrid**: Envio de emails para recuperação de senha
- **Arquitetura Clean**: Separação de concerns com use cases, repositories e entities

## 📋 Funcionalidades

- ✅ Registro de usuários
- ✅ Login com JWT
- ✅ Validação de sessão
- ✅ Recuperação de senha por email
- ✅ Reset de senha com token temporário

## 🛠️ Instalação

### 1. Clone o repositório
```bash
git clone <url-do-repositorio>
cd backend-template
```

### 2. Crie um ambiente virtual
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Instale as dependências
```powershell
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente
Copie o arquivo `.env.example` para `.env` e preencha com suas configurações:
```powershell
Copy-Item .env.example .env
```

Edite o arquivo `.env` com suas credenciais.

### 5. Configure o banco de dados
Certifique-se de que o MySQL está rodando e crie o banco de dados:
```sql
CREATE DATABASE backend_template_db;
```

### 6. Execute as migrações do Alembic
```powershell
# Criar a primeira migração (inicial)
alembic revision --autogenerate -m "Initial migration"

# Aplicar as migrações
alembic upgrade head
```

### 7. Execute a aplicação
```powershell
uvicorn src.app:app --reload
```

A API estará disponível em `http://localhost:8000`

## 📚 Endpoints da API

### Autenticação de Usuários

- **POST** `/user/auth/register` - Registrar novo usuário
  ```json
  {
    "name": "João Silva",
    "email": "joao@example.com",
    "password": "senha123"
  }
  ```

- **POST** `/user/auth/login` - Fazer login
  ```json
  {
    "email": "joao@example.com",
    "password": "senha123"
  }
  ```

- **POST** `/user/auth/check/token` - Validar token de sessão (requer autenticação)

- **POST** `/user/auth/pwd/recovery/email` - Solicitar email de recuperação de senha
  ```json
  {
    "email": "joao@example.com"
  }
  ```

- **POST** `/user/auth/reset/pwd` - Redefinir senha com token
  ```json
  {
    "token": "uuid-do-token",
    "password": "nova_senha123"
  }
  ```

## 🗂️ Estrutura do Projeto

```
backend-template/
├── alembic/                    # Configuração e migrações do Alembic
│   ├── versions/              # Arquivos de migração
│   ├── env.py                 # Configuração do ambiente Alembic
│   └── script.py.mako         # Template para migrações
├── src/
│   ├── app.py                 # Aplicação principal FastAPI
│   ├── config/                # Configurações da aplicação
│   ├── database/              # Configuração do banco de dados
│   │   └── database.py        # SQLAlchemy setup e get_db()
│   ├── entities/              # Entidades Pydantic
│   │   └── user.py           # Entidade User
│   ├── middlewares/           # Middlewares customizados
│   │   └── validate_user_auth_token.py
│   ├── models/                # Modelos SQLAlchemy
│   │   └── user_model.py     # Modelo User para o banco
│   ├── repositories/          # Camada de acesso a dados
│   │   ├── base_repository.py
│   │   └── user_repository.py
│   ├── use_cases/             # Casos de uso (lógica de negócio)
│   │   └── user/
│   │       └── auth/
│   │           ├── login/
│   │           ├── register/
│   │           ├── reset_pwd/
│   │           ├── send_pwd_recovery_email/
│   │           └── check_session_validity/
│   └── utils/                 # Utilitários
│       ├── encode_hmac_hash.py
│       ├── generate_random_pwd.py
│       └── send_email.py
├── alembic.ini               # Configuração do Alembic
├── requirements.txt          # Dependências Python
└── .env.example             # Exemplo de variáveis de ambiente
```

## 🔧 Tecnologias Utilizadas

- **Python 3.10+**
- **FastAPI** - Framework web
- **SQLAlchemy** - ORM
- **Alembic** - Migrações de banco de dados
- **PyMySQL** - Driver MySQL
- **Bcrypt** - Hash de senhas
- **PyJWT** - JSON Web Tokens
- **Pydantic** - Validação de dados
- **SendGrid** - Envio de emails

## 📝 Configuração do Alembic

Para criar uma nova migração após alterar os modelos:
```powershell
alembic revision --autogenerate -m "Descrição da alteração"
```

Para aplicar as migrações:
```powershell
alembic upgrade head
```

Para reverter a última migração:
```powershell
alembic downgrade -1
```

## 🔐 Segurança

- Senhas são hasheadas com bcrypt
- JWT para autenticação stateless
- Tokens de recuperação de senha expiram em 15 minutos
- Limite de 1 solicitação de recuperação de senha por hora

## 🎯 Próximos Passos

Este template pode ser expandido com:
- [ ] Refresh tokens
- [ ] Verificação de email
- [ ] Rate limiting
- [ ] Testes automatizados
- [ ] Docker e docker-compose
- [ ] CI/CD
- [ ] Logging estruturado
- [ ] Métricas e monitoramento

## 📄 Licença

Este projeto é um template livre para uso em projetos da sua empresa.

## 👥 Contribuindo

Sinta-se livre para adaptar este template às necessidades específicas do seu projeto!
