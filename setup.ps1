# Script de setup rápido para o Backend Template
# Execute este script após clonar o repositório

Write-Host "🚀 Iniciando setup do Backend Template..." -ForegroundColor Green

# 1. Criar ambiente virtual
Write-Host "`n📦 Criando ambiente virtual..." -ForegroundColor Yellow
python -m venv venv

# 2. Ativar ambiente virtual
Write-Host "`n✅ Ativando ambiente virtual..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# 3. Instalar dependências
Write-Host "`n📥 Instalando dependências..." -ForegroundColor Yellow
pip install -r requirements.txt

# 4. Copiar arquivo de ambiente
Write-Host "`n📝 Criando arquivo .env..." -ForegroundColor Yellow
if (!(Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "⚠️  IMPORTANTE: Edite o arquivo .env com suas configurações!" -ForegroundColor Red
} else {
    Write-Host "⚠️  Arquivo .env já existe. Não foi sobrescrito." -ForegroundColor Yellow
}

Write-Host "`n📋 Próximos passos:" -ForegroundColor Cyan
Write-Host "1. Edite o arquivo .env com suas credenciais" -ForegroundColor White
Write-Host "2. Certifique-se de que o MySQL está rodando" -ForegroundColor White
Write-Host "3. Crie o banco de dados: CREATE DATABASE backend_template_db;" -ForegroundColor White
Write-Host "4. Execute: alembic revision --autogenerate -m 'Initial migration'" -ForegroundColor White
Write-Host "5. Execute: alembic upgrade head" -ForegroundColor White
Write-Host "6. Execute: uvicorn src.app:app --reload" -ForegroundColor White

Write-Host "`n✨ Setup concluído!" -ForegroundColor Green
