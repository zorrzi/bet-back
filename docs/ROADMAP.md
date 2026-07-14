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
- [x] Ambiente local completo: Postgres via docker-compose, migrations
      aplicadas, API + front rodando (decisão do dono: tudo local antes de
      qualquer deploy; Railway/Vercel ficam para depois)
- [x] Chaves de API do usuário (API-Football + The Odds API) no `.env`
- [x] Fixtures/resultados da temporada corrente via The Odds API
      (autocreate + /scores) — plano free da API-Football não vê 2026
      (ADR-0004)
- [x] **Primeira captura real de odds com timestamp** (2026-07-13: 13
      partidas, 979 snapshots, 23 casas incl. Pinnacle) — critério do ponto
      de controle da spec §13 CUMPRIDO
- [ ] Ligar o scheduler local (`SCHEDULER_ENABLED=true`) e acumular
      histórico de odds por alguns dias/rodadas
- [ ] Deploy no Railway + Vercel — ADIADO por decisão do dono do projeto
- [ ] (deferido p/ quando necessário) ingestão de players/lineups/stats
      detalhados — schema pronto, ingestão entra antes da Fase 7

## Fase 2 — Motor de modelagem ✅

- [x] De-vig multiplicativo + Shin + power (`src/services/devig.py`),
      testes calculados à mão
- [x] Dixon-Coles com decaimento temporal, correção de placares baixos e
      janela de treino de 4 anos (`src/services/modeling/dixon_coles.py`)
- [x] `model_predictions` versionadas (`dixoncoles_v1`); rotas
      POST /matches/{id}/predict, GET /matches/{id}/predictions,
      POST /jobs/predict-upcoming
- [x] Histórico importado: 5.496 partidas 2012–2026 + 15.825 closings da
      Pinnacle via football-data.co.uk (ADR-0005), aliases de times entre
      provedores
- [x] Validação real: 13/13 jogos futuros previstos; sanidade dos
      parâmetros conferida (mando 1.44x, ataques top = Fla/Palmeiras/Botafogo)
- Observação honesta: o modelo diverge bastante da Pinnacle em alguns
  mandantes (+10–30% de "edge" aparente). Isso é o esperado ANTES do
  backtest — o CLV das Fases 4–5 é quem diz se há edge real.

## Fase 3 — Sinais de valor + staking ✅

- [x] Staking puro (`src/services/staking.py`): edge com push, Kelly
      fracionário, teto por aposta — testes calculados à mão
- [x] Geração de `value_bets` (`src/services/value_bet_service.py`):
      fair prob de-vigada da linha sharp, melhor odd entre as casas,
      edge > min_edge E Kelly > 0; regeneração expira candidatos antigos
- [x] Apostas paper: POST /bets valida placed_at < kickoff e debita a
      banca; settle resolve win/loss/push, calcula P&L e CLV
      (closing da mesma seleção, mesma casa → fallback sharp)
- [x] Rotas: GET /value-bets, POST/GET /bets, GET /bankroll,
      POST /jobs/generate-signals, POST /jobs/settle + jobs no scheduler
- [x] Validação real: 12 sinais candidatos gerados sobre os 13 jogos
- Quarter lines (2.25/2.75): fora das previsões; precificação por
  decomposição fica como melhoria futura da Fase 3

## Fase 4 — Backtest com CLV ✅ (engine) / veredito: modelo v1 refutado

- [x] Loop cronológico sem informação do futuro (refit mensal com
      warm-start, cutoff = kickoff)
- [x] Out-of-sample por construção; janela avaliada nunca treina o próprio
      modelo
- [x] Métricas CLV-first + ROI, P&L, drawdown, Sharpe; rotas POST/GET
      /backtests (assíncrono, status running/finished/failed)
- [x] **Run real (id=1)**: 737 apostas 2024–2026 → ROI −22,7%, Sharpe −3,0.
      `dixoncoles_v1` NÃO bate a closing line (ADR-0006). Nenhuma aposta
      com este modelo; o feed de sinais atual é inválido até o v2.
- [x] `dixoncoles_v2` (blend): calibrado por log-loss em 2022–2023 —
      **mercado puro venceu** (w→0 melhora calibração; ROI negativo em
      todo w; OOS w=0.2: −4,1%). Produção usa w=0.1; sinais vivos =
      line-shopping vs sharp; CLV do paper trading é o árbitro (ADR-0007)
- Nota: CLV estrutural = 0 neste corpus (só closing odds); CLV real será
  medido no paper trading com as capturas ao vivo (ADR-0006)

## Fase 5 — Paper trading (forward test)

- [ ] Registro pré-jogo automático, settle pós-jogo, CLV por aposta
- [ ] Centenas de bets antes de qualquer conclusão

## Fase 6 — Frontend (React + Vite, skill frontend-design) ✅

- [x] Design system próprio (tokens verde-noturno, dourado = sharp/closing,
      verde/vermelho semânticos com rótulo, Saira/Inter/Plex Mono)
- [x] Assinatura: régua de probabilidade (fair vs decisão) nos sinais
- [x] Páginas: Partidas, Detalhe (modelo vs mercado), Sinais (com registro
      paper + aviso ADR-0007), Banca (CLV acumulado acima da equity),
      Backtests (CLV primeiro + curva simulada)
- [x] Estados completos (loading/empty/error), disclaimer permanente
- [ ] Testes de componente (Vitest + Testing Library) — pendente

## Fase 7 — Props e combinadas (só após CLV positivo comprovado)

- [ ] Ingestão player_match_stats/lineups; modelos de taxa por 90min;
      correlação tratada explicitamente
