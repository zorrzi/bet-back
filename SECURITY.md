# SECURITY.md

## Segredos

- Nunca commitar chaves, tokens ou `DATABASE_URL`. Tudo via variáveis de
  ambiente; `.env` está no `.gitignore`; `.env.example` documenta as chaves
  **sem valores**.
- Se um segredo vazar em commit: **rotacione imediatamente** (gerar chave
  nova no provedor / Railway) — remover do histórico não basta.
- Segredos nunca aparecem em logs (logging estruturado não recebe chaves).

## Superfície de ataque e mitigação

- **Rotas de escrita** (`/jobs/*`, futuras `/bets`, `/backtests`): exigem
  header `X-API-Key` == `API_KEY`. Em `ENVIRONMENT=prod`, `API_KEY` vazia
  derruba o startup (fail-closed).
- **CORS**: origens explícitas via `CORS_ORIGINS` (domínio da Vercel em
  prod). Nunca `*`.
- **Rate limiting**: slowapi nas rotas públicas.
- **Validação de entrada**: 100% Pydantic; parâmetros de query tipados e
  limitados (`limit ≤ 200`).
- **SQL**: exclusivamente ORM/parametrizado. Zero string-building.
- **Chamadas externas**: timeout + retry com backoff exponencial (tenacity),
  respeitando limites dos planos dos provedores.
- **Erros**: handler global devolve mensagem genérica; stack trace só no log.

## Dependências

- Versões fixadas em `requirements.txt`/`requirements-dev.txt`.
- `pip-audit` roda no CI em cada push; vulnerabilidade conhecida bloqueia
  merge.

## Processo

- Rodar a skill `security-guidance` antes de cada deploy e ao mexer em auth,
  segredos, CORS, rotas públicas ou dependências novas (spec §10.1).
- Deploy: variáveis configuradas no Railway/Vercel, nunca no código.
