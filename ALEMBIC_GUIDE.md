# Guia de Uso do Alembic

## O que é o Alembic?

Alembic é uma ferramenta de migração de banco de dados para SQLAlchemy. Ele permite versionar e gerenciar mudanças no esquema do banco de dados de forma controlada.

## Comandos Principais

### 1. Criar uma Nova Migração

Após alterar os modelos em `src/models/`, crie uma migração automática:

```powershell
alembic revision --autogenerate -m "Descrição da alteração"
```

Exemplo:
```powershell
alembic revision --autogenerate -m "Add phone field to users table"
```

### 2. Aplicar Migrações

Para aplicar todas as migrações pendentes:

```powershell
alembic upgrade head
```

### 3. Reverter Migrações

Reverter a última migração:
```powershell
alembic downgrade -1
```

Reverter para uma revisão específica:
```powershell
alembic downgrade <revision_id>
```

Reverter todas as migrações:
```powershell
alembic downgrade base
```

### 4. Ver Histórico de Migrações

Ver o histórico completo:
```powershell
alembic history
```

Ver a revisão atual:
```powershell
alembic current
```

### 5. Criar Migração Manual (Vazia)

Se precisar criar uma migração manualmente:
```powershell
alembic revision -m "Descrição"
```

## Workflow Recomendado

### Adicionando um Novo Campo ao Modelo User

1. **Edite o modelo** (`src/models/user_model.py`):
```python
from sqlalchemy import Column, String

class UserModel(Base):
    # ... campos existentes ...
    phone = Column(String(20), nullable=True)  # Novo campo
```

2. **Crie a migração**:
```powershell
alembic revision --autogenerate -m "Add phone field to users"
```

3. **Revise o arquivo de migração** gerado em `alembic/versions/`:
   - Verifique se o upgrade e downgrade estão corretos
   - Faça ajustes se necessário

4. **Aplique a migração**:
```powershell
alembic upgrade head
```

### Criando uma Nova Tabela

1. **Crie o modelo** em `src/models/`:
```python
from sqlalchemy import Column, Integer, String
from src.database.database import Base

class ProductModel(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    price = Column(Integer, nullable=False)
```

2. **Importe o modelo** no `alembic/env.py`:
```python
from models.product_model import ProductModel
```

3. **Crie e aplique a migração**:
```powershell
alembic revision --autogenerate -m "Create products table"
alembic upgrade head
```

## Estrutura de uma Migração

```python
"""Add phone field to users

Revision ID: abc123def456
Revises: previous_revision
Create Date: 2025-10-20 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'abc123def456'
down_revision = 'previous_revision'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Mudanças a serem aplicadas
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))


def downgrade() -> None:
    # Como reverter as mudanças
    op.drop_column('users', 'phone')
```

## Dicas Importantes

### ✅ Boas Práticas

1. **Sempre revise** as migrações geradas automaticamente
2. **Teste** as migrações em ambiente de desenvolvimento primeiro
3. **Faça backup** do banco antes de aplicar migrações em produção
4. **Use mensagens descritivas** nas migrações
5. **Commit** os arquivos de migração no controle de versão

### ⚠️ Cuidados

1. **Nunca edite** migrações que já foram aplicadas em produção
2. **Não delete** arquivos de migração aplicados
3. **Cuidado com** operações destrutivas (drop table, drop column)
4. **Sempre implemente** tanto `upgrade()` quanto `downgrade()`

## Troubleshooting

### Erro: "Can't locate revision identified by 'xyz'"

Solução: Verifique se todos os arquivos de migração estão presentes em `alembic/versions/`

### Erro: "Target database is not up to date"

Solução: Execute `alembic upgrade head` para aplicar migrações pendentes

### Autogenerate não detecta mudanças

Possíveis causas:
- Modelo não foi importado no `alembic/env.py`
- Mudança não é detectável automaticamente (ex: índices, constraints)
- Base.metadata não está atualizado

### Resetar completamente o banco

```powershell
# 1. Reverter todas as migrações
alembic downgrade base

# 2. Deletar o banco de dados
# DROP DATABASE backend_template_db;
# CREATE DATABASE backend_template_db;

# 3. Reaplicar todas as migrações
alembic upgrade head
```

## Integração com CI/CD

Para ambientes de produção, adicione ao seu pipeline:

```powershell
# Verificar se há migrações pendentes
alembic current

# Aplicar migrações automaticamente
alembic upgrade head
```

## Referências

- [Documentação oficial do Alembic](https://alembic.sqlalchemy.org/)
- [Tutorial Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
