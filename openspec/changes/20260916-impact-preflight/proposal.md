# Proposal — 20260916-impact-preflight

## Contexto

v0.4 Change 0 (`20260916-kdd-enforceable-checks`) cerró con checks científicos deterministas. Este
Change 1 ataca un problema distinto: hoy, antes de este change, un cambio en un símbolo/contrato
compartido se descubre reactivamente (correr tests/notebooks, ver qué falla, arreglar, repetir).
Impact Preflight adelanta esa señal de forma estática, ANTES de ejecutar nada.

Principio permanente (igual que Change 0): el binario encuentra relaciones/referencias
deterministas; el LLM/Lead decide si el impacto es semánticamente real. El resultado nunca afirma
"esto está roto" — siempre "potentially affected".

## Qué se construye

Paquete nuevo `tools/dsimpact/` (mismo patrón de paquete top-level que `tools/ds_profile/`, con
dependencia unidireccional hacia `tools/dsguard/` para reusar `repo.py`/`notebooks.py`, nunca al
revés):

1. Extracción de "changed items" desde un diff de Git (`--since REF` o `--staged`): archivos
   agregados/modificados/eliminados/renombrados; símbolos Python de nivel módulo (función/clase/
   constante) cuyo cuerpo cambió; strings "contractuales" en posición estructural (listas/tuplas/
   dicts/asignaciones/asserts/comparaciones) que cambiaron.
2. Búsqueda de consumidores potenciales de esos changed items sobre el universo de archivos
   trackeados/no-ignorados del repo (`.py`, `.ipynb`, `.json`, `.yaml`/`.yml`, `.toml`, `.md`),
   con evidencia estructural (no substring ciego) y clasificación por tipo de evidencia.
3. CLI: `python -m tools.dsimpact scan --since <REF> [--json]` /
   `python -m tools.dsimpact scan --staged [--json]`, más un wrapper fino
   `python -m tools.ds_guard impact scan ...` (misma implementación canónica, sin duplicar lógica).
4. Filtro determinista de tokens genéricos (denylist corta + longitud mínima) para evitar ruido
   masivo.
5. Lead: sección nueva en `methodology.md` (+ `.tmpl`) sobre cuándo correr `dsimpact scan` — nunca
   obligatorio para cambios triviales, nunca delegado a un subagente solo para correrlo.
6. Manifest: entrada(s) VERBATIM para `tools/dsimpact/*`, `stage_minimo="experiment"`.

## Qué NO se construye (fuera de alcance explícito)

Scope & Change Isolation / enforcement de scope (Change 2), Portable Core, token governance,
reporting, harmessi-bench, multi-provider, nuevos readiness gates, nuevos scientific checks,
dependency graph persistente, auto-fix/auto-edit de consumidores, ejecución automática de
tests/notebooks, call graph completo, semantic analyzer, language server, análisis LLM/dinámico,
parser SQL general, lineage engine, cache/daemon/indexador background, embeddings, dependencias
nuevas (tree-sitter/ripgrep/PyYAML/etc — solo stdlib).

## Decisión/deuda registrada (para changes futuros)

- No hay parser real de YAML/TOML (no hay soporte stdlib universal para el rango de Python
  soportado) — se tratan como texto plano con matching conservador, documentado como límite
  conocido, no bloqueante para v1.
- Si `dsimpact` debe convertirse en gate (exit != 0 con findings, o wireado a SDD/readiness), eso
  es una decisión de un change posterior — Change 1 es estrictamente informativo.
