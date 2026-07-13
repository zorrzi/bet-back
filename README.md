# betting-backend

Backend da plataforma de análise de valor em apostas esportivas (futebol).

O sistema estima probabilidades próprias por partida e as compara com a
probabilidade implícita do mercado **após remoção da margem** (de-vig, com a
Pinnacle como referência sharp). Só existe sinal quando há **EV positivo**
(`edge = model_prob × odd − 1 > min_edge`). A métrica principal do projeto é
**CLV (Closing Line Value)** — não o lucro.

> ⚠️ Este é um projeto de análise/estudo. Apostas envolvem risco e nenhum
> resultado é garantido. Edge sustentável é raro; trate lucro como hipótese
> a ser refutada.

## Stack

FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL · Pydantic v2 · APScheduler ·
pytest · ruff · mypy (strict). Deploy: Railway. Frontend: [bet-front]
(React + Vite, Vercel).

## Subir localmente

Pré-requisitos: Python 3.12+ e um PostgreSQL acessível (ou use SQLite p/ testes).

```powershell
# 1. venv + dependências
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 2. configuração
Copy-Item .env.example .env
# edite .env: DATABASE_URL, API_FOOTBALL_KEY, THE_ODDS_API_KEY

# 3. migrations
.\.venv\Scripts\python.exe -m alembic upgrade head

# 4. rodar
.\.venv\Scripts\python.exe -m uvicorn src.app:app --reload
# docs interativas: http://localhost:8000/docs
```

## Variáveis de ambiente

Documentadas em [.env.example](.env.example). Principais:

| Variável | Descrição |
|---|---|
| `DATABASE_URL` | conexão Postgres (Railway fornece em prod) |
| `API_KEY` | protege rotas de escrita (`X-API-Key`); obrigatória em prod |
| `API_FOOTBALL_KEY` | chave da API-Football (fixtures/resultados) |
| `THE_ODDS_API_KEY` | chave da The Odds API (odds, incl. Pinnacle) |
| `CORS_ORIGINS` | origens permitidas, separadas por vírgula |
| `SCHEDULER_ENABLED` | liga os jobs periódicos de ingestão |

Nunca commitar `.env` ou segredos (ver [SECURITY.md](SECURITY.md)).

## Testes e qualidade

```powershell
.\.venv\Scripts\python.exe -m pytest          # suíte + cobertura
.\.venv\Scripts\python.exe -m ruff check .    # lint
.\.venv\Scripts\python.exe -m mypy            # type-check
```

CI (GitHub Actions) roda lint, type-check, testes e auditoria de dependências
em cada push/PR.

## Arquitetura em alto nível

```
provedores externos ──► services de ingestão ──► PostgreSQL (odds append-only)
      ▲                                              │
  APScheduler (jobs)                                 ▼
                       FastAPI (rotas de leitura + jobs) ──► frontend
```

Camadas: `routers → services → repositories → models` (+ `schemas`,
`providers`, `config`). Detalhes em [ARCHITECTURE.md](ARCHITECTURE.md).

## Documentação

- [CLAUDE.md](CLAUDE.md) — instruções operacionais para o agente
- [ARCHITECTURE.md](ARCHITECTURE.md) — camadas, fluxo de dados, porquês
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — schema e racional
- [docs/DOMAIN.md](docs/DOMAIN.md) — glossário: vig, de-vig, EV, Kelly, CLV
- [docs/ROADMAP.md](docs/ROADMAP.md) — faseamento e progresso
- [docs/decisions/](docs/decisions/) — ADRs
- [SECURITY.md](SECURITY.md) · [CONTRIBUTING.md](CONTRIBUTING.md)
