# ADR-0006 — Backtest sobre closing lines e o veredito do dixoncoles_v1

**Data:** 2026-07-13 · **Status:** aceito

## Contexto: CLV estrutural zero neste corpus

O histórico do Brasileirão (football-data.co.uk) traz **apenas closing
odds** da Pinnacle. O backtest simula apostar NO preço de fechamento, logo
`clv = taken/closing − 1 = 0` por construção. A métrica discriminante deste
dataset é o **ROI contra a closing line** — teste mais duro que CLV > 0:
lucrar contra o preço mais eficiente que existe implica edge real. O CLV
"de verdade" passa a ser medível no paper trading (Fase 5), onde capturamos
odds ao vivo antes do fechamento. A engine já computa CLV genericamente e
o reportará assim que houver dados com pré-fechamento.

## O run (id=1, out-of-sample honesto)

- Janela avaliada: 2024-01-01 → 2026-07-13 (~2,5 temporadas, 737 apostas)
- Treino: refit mensal com cutoff = kickoff (nenhuma informação do futuro);
  calibração implícita em 2012–2023 + janela rolante de 4 anos
- Parâmetros: min_edge 3%, Kelly 0.25x, teto 2%/aposta

## Veredito: dixoncoles_v1 NÃO bate a closing line

| Métrica | Valor |
|---|---|
| ROI | **−22,7%** |
| P&L total | −869 (banca 1000) |
| Max drawdown | 973 |
| Sharpe | −2,99 |

Decomposição: modelo sistematicamente sobreconfiante vs mercado (AWAY:
modelo 29,7% médio vs fair 22,0%; HOME: 47,7% vs 38,4%). As maiores perdas
estão nos maiores "edges" aparentes (AWAY, edge médio 34% → −579) —
**seleção adversa clássica**: quanto mais o modelo discorda da Pinnacle,
mais provável que o erro seja do modelo.

## Consequências

1. **Nenhuma aposta (nem paper) com o v1.** O feed de value_bets atual
   deriva do modelo refutado e deve ser tratado como inválido.
2. Próxima iteração (`dixoncoles_v2`): **calibração/shrinkage para o
   mercado** — p_final = w·p_modelo + (1−w)·p_fair com w ajustado no
   período de calibração e validado out-of-sample no mesmo harness. Com w
   honesto, a maioria dos sinais desaparece — "sem valor → sem aposta" é o
   comportamento correto (spec §12).
3. Este resultado é o sistema FUNCIONANDO: o pipeline disciplinado refutou
   a hipótese de lucro antes de qualquer dinheiro, que é exatamente o valor
   primário do projeto (spec §12, realismo).
