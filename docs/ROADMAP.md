# ROADMAP.md — faseamento (spec §1)

Cada fase deve estar funcional e testável antes da próxima. CLV é a métrica
de aprovação entre fases.

## Fase 1 — Fundação de dados ✅ (código) / ⏳ (operação)

- [x] Limpeza do template (domínio de auth removido)
- [x] Governança (§10): CLAUDE.md, README, ARCHITECTURE, DATA_MODEL, DOMAIN,
      SECURITY, CONTRIBUTING, ROADMAP, ADRs
- [x] Base de engenharia (§11): camadas, Settings, ruff+mypy strict, pytest,
      CI, health check, logging JSON
- [x] Schema §4 completo (15 tabelas) com migration + testes (up/down)
- [x] Providers: API-Football (fixtures/resultados) e The Odds API (odds)
- [x] Ingestão idempotente de fixtures + snapshots de odds append-only
- [x] Job mark-closing (closing line por bookmaker/market/selection)
- [ ] Deploy no Railway (Postgres) — requer conta/credenciais
- [ ] Chaves de API do usuário (API-Football + The Odds API)
- [ ] Primeira captura real de odds com timestamp (critério do ponto de
      controle da spec §13)
- [ ] (deferido p/ quando necessário) ingestão de players/lineups/stats
      detalhados — schema pronto, ingestão entra antes da Fase 7

## Fase 2 — Motor de modelagem

- [ ] De-vig multiplicativo (+ Shin/power configuráveis) sobre linha sharp
- [ ] Dixon-Coles (ataque/defesa/casa, correção de placares baixos,
      decaimento temporal) via scipy
- [ ] `model_predictions` versionadas; rotas predict
- [ ] Histórico p/ calibração: CSVs football-data.co.uk (closing Pinnacle
      grátis — ver ADR-0002)

## Fase 3 — Sinais de valor + staking

- [ ] Geração de `value_bets` (edge > min_edge)
- [ ] Kelly fracionário + max_stake_pct
- [ ] Rotas /value-bets, POST /bets (placed_at < kickoff), /bankroll

## Fase 4 — Backtest com CLV

- [ ] Loop cronológico sem informação do futuro
- [ ] Calibração vs validação out-of-sample
- [ ] Métricas: avg_clv, pct_positive_clv (principais), ROI, P&L, drawdown

## Fase 5 — Paper trading (forward test)

- [ ] Registro pré-jogo automático, settle pós-jogo, CLV por aposta
- [ ] Centenas de bets antes de qualquer conclusão

## Fase 6 — Frontend (React + Vite, skill frontend-design)

- [ ] Partidas, detalhe c/ mercados (modelo vs mercado), sinais, banca
      (curva de CLV com destaque ≥ equity), backtests

## Fase 7 — Props e combinadas (só após CLV positivo comprovado)

- [ ] Ingestão player_match_stats/lineups; modelos de taxa por 90min;
      correlação tratada explicitamente
