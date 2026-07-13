# ADR-0001 — Liga inicial: Brasileirão Série A

**Data:** 2026-07-13 · **Status:** aceito

## Contexto

A spec (§3) manda validar o pipeline ponta a ponta com UMA liga bem coberta
antes de escalar, sugerindo Brasileirão ou Premier League.

## Decisão

Brasileirão Série A 2026 (API-Football liga `71`; The Odds API
`soccer_brazil_campeonato`).

## Racional

- **Está em temporada em julho/2026** (abril–dezembro); a Premier League está
  de férias até agosto — com o Brasileirão o pipeline captura odds reais
  imediatamente, que é o critério do ponto de controle.
- Cobertura confirmada nos dois provedores (verificado 2026-07-13), incluindo
  Pinnacle via The Odds API região `eu`.
- football-data.co.uk tem histórico do Brasileirão desde 2012 com closing
  1X2 da Pinnacle (grátis) para o backtest da Fase 4.

## Consequências

- Config default aponta para liga 71 / temporada 2026 (`settings.py`).
- Trocar/adicionar liga = mudar env vars, sem mudança de código.
