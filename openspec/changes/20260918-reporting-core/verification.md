# Verificación — 20260918-reporting-core

## Evidencia obtenida

- **Tests del Change** (`pytest tools/reporting/tests tools/tests/test_v06_core_neutrality.py tools/tests/test_architecture_boundaries.py tools/tests/test_v05_core_neutrality.py tools/tests/test_manifest_dsguard_parity.py tools/ds_init/tests/test_manifest.py`):
  - 1ª corrida (antes de la revisión): `128 passed`, 90 subtests.
  - Tras los fixes del reviewer: `150 passed, 1 skipped` (el golden), 131 subtests, en `2.44s`.
  - Con el golden fijado (`HASH_ESPERADO`) pasan a 151 passed, 0 skipped; el Lead lo re-confirma en el cierre.
- **Suites que consumen `MANIFEST` sin filtro de stage** (`tools/ds_init/tests/test_control_file.py` + `tools/harmessi/tests/test_doctor.py`): `94 passed` en `486.30s`. Corrida anterior a los fixes; los fixes no tocaron `manifest.py`.
- **Paridad de manifest** (`python -m tools.ds_init.check_manifest_parity`): `[OK] Todas las rutas VERBATIM del manifiesto existen`.
- **Reviewer** (`data-science-reviewer`, ciclo 1 de 2): APRUEBA CON FIXES. 0 bloqueantes, 3 importantes, 6 menores, 3 cosméticos. Los hallazgos 1–12 se aplicaron (A–M):
  - Política de estabilidad del hash: docstring del módulo + sección en `design.md` + test golden de claves de `to_dict()` y del hash.
  - Celdas `NaT`/`NA` en `from_frame`: cualquier objeto con `x != x` pasa a `None` antes de la rama `isoformat()`.
  - Ids reservados de Windows (`con`, `prn`, `aux`, `nul`, `com1..9`, `lpt1..9`) rechazados en `_validar_id`.
  - `from_frame` captura `AttributeError`/`TypeError`/`ValueError` (`columns=None`, `item()` multi-elemento); metadata circular (`RecursionError`) es `ReportingContractError`.
  - Celdas con tipos nativos (`bool`/`int`/`float`/`str`), sin retener subclases externas.
  - Docstrings: `from_frame` ("objeto tabular"), literal `"eda"` como valor de vocabulario, helpers privados; anotaciones `-> Iterator[...]` en `iter_*`.
  - `design.md`: riesgo `True == 1 == 1.0` (identidad de contenido = hash, no `==`).
  - Tests: robustez de coerción, ids reservados en los 5 contratos, chequeos de tipo, `FrozenInstanceError`, orden de accesores, `backend_payload` sin estado interno.
  - Neutralidad: sanity de los detectores (whitelist, identificadores, estilos de import de `reporting`), `__init__.py` vacío, `MODULOS_CORE` incluye el core; test literal de `canonical_json`.
  - Único ítem no aplicado: el test "subsumido" de neutralidad no se pudo identificar con certeza; se conserva, sin costo.
- **Sweep de privacidad**: grep de nombres, rutas y emails privados en `tools/reporting`, `tools/tests/test_v06_core_neutrality.py`, este Change, `ARCHITECTURE.md` y `docs/roadmap/v0.6.md` → 0 fugas (solo coincidencias en `.pyc` ignorados por git).
- **Diff real vs alcance**: 4 archivos preexistentes modificados, todos aditivos y dentro del alcance: `ARCHITECTURE.md` (+6), `docs/roadmap/v0.6.md` (2 líneas), `tools/ds_init/manifest.py` (+12), `tools/tests/test_architecture_boundaries.py` (+1). Nuevos: `tools/reporting/**`, `tools/tests/test_v06_core_neutrality.py` y los artefactos del Change.

## Fingerprint de dataset/artefacto

No aplica -- contrato en memoria de infraestructura del harness, sin dataset.

## Diferencias contra la spec

Enmiendas durante el Change, todas registradas en `spec.md`/`design.md` y re-aprobadas por hash:
- R5: `from_frame` usa `astype(object)` si existe (fallback `values.tolist()`).
- R4: ids seguros también en Windows (nombres de dispositivo reservados rechazados).
- R5: objeto con `x != x` → `None` y valores nativos en las celdas.
- `design.md`: política de evolución del esquema (todo campo nuevo en `to_dict()` exige bump de `SCHEMA_VERSION`).

## Limitaciones

1. La validación semántica/evidencial (referencias, columnas, claims) NO está en este Change: es del Change 3.
2. `from_frame` solo se probó con dobles de prueba; pandas no está instalado en el entorno y no se instala.
3. `==` no es identidad de contenido (`True == 1 == 1.0` en tuplas): la identidad es `content_sha256()`.
4. Se cubren los nombres reservados de Windows; otros SO no aplican.

## Pendientes derivados

- Change 3 debe hashear los BYTES persistidos de cada artefacto, además del hash de contenido del objeto.
- Los ids se usan como nombres de archivo en `artifacts/`: los Changes 1–4 deben tratarlos así.
- Cambiar `HASH_ESPERADO` o las claves de `to_dict()` exige bump de `SCHEMA_VERSION`.

## Resultado final

**CERRADO — Change 0 cumple R1–R17.**
