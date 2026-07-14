# ADR-0007 — Blend calibrado: o mercado vence; a estratégia viva é line-shopping

**Data:** 2026-07-13 · **Status:** aceito · **Continua:** ADR-0006

## O experimento

`p_decisão = w·p_modelo + (1−w)·p_fair` (shrinkage para o mercado).
Calibração por **log-loss** (scoring rule própria — não ROI) em 2022–2023
(760 partidas, refit mensal, sem informação do futuro); validação
out-of-sample em 2024–2026.

## Resultados

| w | log-loss (calib) | ROI (calib) | n bets |
|---|---|---|---|
| **0.0 (mercado puro)** | **1.0152** | — | 0 |
| 0.1 | 1.0157 | −22,2% | 72 |
| 0.2 | 1.0166 | −4,8% | 245 |
| 0.4 | 1.0196 | −6,0% | 507 |
| 0.6 | 1.0240 | −5,4% | 646 |
| 1.0 (v1) | — | −22,7% (OOS) | 737 |

Validação OOS (2024–2026, w=0.2): ROI **−4,1%** (262 apostas) ≈ o custo do
vig. Log-loss melhora monotonicamente conforme w→0.

## Conclusões (honestas)

1. **O Dixon-Coles sobre placares públicos não adiciona informação além da
   closing line da Pinnacle.** Qualquer peso positivo piora a calibração.
   Era o resultado mais provável a priori (spec §0: recalcular a
   estatística melhor que a Pinnacle é praticamente impossível) — agora
   está demonstrado nos nossos dados.
2. **Apostar contra a closing por divergência de modelo está vetado** —
   em qualquer w.
3. **A estratégia que permanece em pé — e que o backtest NÃO consegue
   testar — é line-shopping:** melhor preço entre as ~23 casas soft vs
   fair prob da linha sharp, capturado dias antes do fechamento. O corpus
   histórico não tem preços de casas soft nem pré-fechamento; o pipeline
   ao vivo tem os dois. O **CLV do paper trading (Fase 5) é o árbitro**.

## Decisões

- `model_blend_weight = 0.1` em produção (indistinguível de w=0 no
  log-loss; mantém voz mínima do modelo para diagnóstico). Sinais vivos
  passam a ser dominados por discrepância de preço vs sharp, não por
  opinião do modelo.
- Melhorias de modelo (xG, escalações, mercado de transferências) só
  entram se baterem o log-loss do mercado neste mesmo harness.
