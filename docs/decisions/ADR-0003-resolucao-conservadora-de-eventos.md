# ADR-0003 — Resolução conservadora de eventos entre provedores

**Data:** 2026-07-13 · **Status:** aceito

## Contexto

The Odds API e API-Football não compartilham IDs de partida. Odds chegam com
nomes de times e horário; fixtures têm IDs próprios. Atribuir odds à partida
errada corromperia silenciosamente EV e CLV — pior que perder o snapshot.

## Decisão

Resolver evento→partida por **kickoff + igualdade de nomes (case-insensitive)**
e **nunca adivinhar**: evento não resolvido é logado
(`odds_ingestion.event_unmatched`) e pulado; o contador `events_unmatched`
aparece na resposta do job para monitoramento.

## Consequências

- Divergências de grafia entre provedores ("Sao Paulo" vs "São Paulo")
  causam perda de snapshots — visível no log/contador, corrigível com tabela
  de aliases (planejada como evolução assim que a primeira captura real
  mostrar quais nomes divergem).
- Falso-positivo (odds na partida errada): praticamente impossível por
  construção. Este é o trade-off desejado.
