# Portabilidad — inventario de auditoría (v0.13 Change 4)

Inventario vivo de supuestos de plataforma en `tools/**`. Estados: `resuelto`, `cubierto por test`, `deuda`.

## Matriz de validación (honesta)

| Plataforma | Estado |
|---|---|
| Windows | **Real**: desarrollo y tests ejecutados en este host. |
| Linux | Contrato / CI: no validado por ejecución en este release. |
| macOS | Contrato / CI: no validado por ejecución en este release. |

El workflow `.github/workflows/portability-smoke.yml` existe y fue verificado estructuralmente (`tools/tests/test_v013_ci_workflow.py`); su ejecución remota no fue observada. Ninguna afirmación de este documento sobre Linux/macOS proviene de una corrida.

## Tabla de auditoría

| Área | Hallazgo | Acción en v0.13 | Estado |
|---|---|---|---|
| Paths / pathlib | Los módulos v0.13 usan `pathlib`; `suite._resolver_cases_file` acepta `\` y `/` en `cases_file` y rechaza absolutos y `..`. Quedan literales con `/` en rutas relativas (`.harmessi/evals`), válidos en todos los SO. | Test AST: sin `\` ni `/tmp` ni `C:\` en literales de ruta de los módulos v0.13. | cubierto por test |
| Paths heredados | Módulos anteriores a v0.13 no auditados uno a uno. | Sin reescritura. | deuda |
| subprocess | `dsguard.repo._git` usa lista de argumentos, captura en bytes y decodifica a mano; `git` ausente => `RuntimeError`. | `dsimpact.git_source` traduce ese error a `GitSourceError`. Test de subprocess con salida Unicode como bytes. | cubierto por test |
| Encodings | Los módulos v0.13 leen/escriben texto con `encoding=` explícito (JSON con `utf-8-sig` al leer). | Test AST (R10). Hay `open(`/`read_text(`/`write_text(` en módulos heredados (`ds_guard`, `doctor`, `cards`, `reporting`, etc.) sin revisar uno a uno. | cubierto por test (v0.13) / deuda (heredado) |
| Finales de línea | Los hashes de skills/superficies normalizan CRLF/CR a LF; `suite_hash` se calcula sobre el contenido parseado. | Smoke: hashes invariantes entre CRLF y LF. | cubierto por test |
| Shell | Sin `shell=True` ni `os.system` en los módulos v0.13 (el chequeo de `providers.conformance` lo menciona solo como texto). | Test AST. No se auditó el resto de `tools/**` de forma exhaustiva. | cubierto por test (v0.13) / deuda (heredado) |
| Lookup de ejecutables | Los adapters usan `shutil.which`; con Python/Git en PATH. | Los tests de conformance usan dobles; sin ejecución real de CLIs de proveedores en CI. | cubierto por test (contrato) |
| Temp dirs | Los tests usan `tempfile`; sin `/tmp` ni `C:\` en módulos v0.13. | Smoke con `TemporaryDirectory`. | cubierto por test |
| Symlinks / junctions | Sin tratamiento especial; la creación de symlink requiere privilegios en Windows. | Smoke con `os.symlink`; el test puede saltarse (skip explícito) sin privilegios o si el SO no lo permite. Junctions no ejercitadas. | cubierto por test (symlink) / deuda (junction) |
| Consola | Consola Windows con codepage no UTF-8 degradaba tildes y podía lanzar `UnicodeEncodeError`. | `_consola_segura()` en `harmessi_bench.cli` y `providers.conformance` (R8) con test cp1252. Otras CLIs (`ds_guard`, `doctor`, `ds_profile`...) no se tocaron. | resuelto (CLIs nuevas) / deuda (heredadas) |
| Git | Rutas con Unicode/espacios dependen de `core.quotepath`; `dsguard.repo` usa `-z`. `dsimpact` era fail-open ante contenido ilegible. | Fail-closed por status (R1–R4), incluido `validar_ref` con git ausente; stderr de git saneado (ruta del repo => `<repo>`); status `U`/`T` con `--staged` se trata como `modified` y falla cerrado si el blob falta (cubierto por test). Smoke en repo temporal con espacios y Unicode. `leer_en_commit` sigue fail-open por diseño documentado. **Parcial:** un consumidor ilegible, ausente o con sintaxis/JSON inválido no aborta el scan: se lista en `summary.consumidores_no_analizados` (y los cambios no analizables en `cambios_no_analizados`) y la CLI avisa «resultado no concluyente»; el análisis de ese consumidor no se realiza. | parcial / cubierto por test |
| Consola (dsimpact) | La CLI `dsimpact` no usa consola segura. Además, `errors="replace"` en las CLIs nuevas puede alterar caracteres de la salida `--json` en consolas no UTF-8. | Sin cambios. | deuda |
| Variables de entorno | `providers.conformance` planta secretos sintéticos con `mock.patch.dict`; los tests de runmanifest leen `USERNAME`/`USER`. Otros módulos leen `os.environ` (p. ej. `doctor`, `launcher_common`, `leadrun`). | Sin cambios. | deuda (revisión por módulo) |

## Fuera de alcance de v0.13

Soporte POSIX completo, validación en Linux/macOS, suite completa en CI y ejecución de Actions.
