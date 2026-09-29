"""Observer de archivos locales sobre `ds_profile` (v0.8 Change 1,
`20260928-source-neutral-data-access`, spec R28).

Único observer que Harmessi incluye (compatibilidad con perfiles
`ds_profile`). Contrato genérico de observer (R15): `factory(source_id,
options) -> observer` con `.capabilities()` y `.observe(request)`, frontera
JSON (los dicts que entran/salen no son tipos de Harmessi).

`ds_profile` se importa de forma PEREZOSA, siempre dentro de funciones/
métodos, nunca a nivel de módulo: así este archivo puede convivir en
`discovery` (stage mínimo del paquete `datasources`, R38) sin forzar que
`ds_profile` esté instalado; solo lo necesita quien realmente llama
`observe()` (stage `experiment`).

## Decisión de diseño: cómo llega `repo_root` (dentro del margen de esta tarea)

El contrato de observer que espera `runtime.py` (otra invocación, T4 en
paralelo) es `factory(source_id, options) -> observer`: no hay forma de
pasarle `repo_root` explícito en esa firma. `verificar_permitido` (guard de
holdout) y la resolución de `options["path"]` (repo-relativa) SÍ necesitan
`repo_root`. Se dejan **dos** puntos de entrada, y se documenta cuál es el
recomendado para que la invocación de T6 (CLI/composición real) elija sin
tener que tocar este archivo:

- `factory_with_repo_root(repo_root)` -- **RECOMENDADO**. Devuelve un
  `factory(source_id, options)` normal (closure) ya atado a `repo_root`. Es
  la opción más limpia: no requiere que quien arme el registro real
  contamine `options` (que es JSON opaco de proyecto, R4) con una clave
  privada de infraestructura.
- `factory(source_id, options)` -- alternativa de compatibilidad directa con
  la firma pedida por R15/R28 tal cual, que toma `repo_root` de
  `options["_repo_root"]` si está presente (clave inyectada por quien
  compone el registro real de `options` antes de llamar a `factory`; NO es
  una opción pública de `.harmessi/sources.json`, es un detalle de
  composición). Si `options["_repo_root"]` falta, `observe()` falla con un
  `RuntimeError` claro en vez de asumir un directorio.

Ambas construyen la misma clase `FileObserver`.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional

from . import profile_bridge

_DATASET_FACETS_SOPORTADAS = ("schema", "row_count", "fingerprint")
_FIELD_FACETS_SOPORTADAS = ("null_count", "distinct_count", "value_distribution", "value_range", "time_range")

_DEFAULTS_GENERAR_PERFIL = {
    "max_filas_exactas": 2_000_000,
    "max_mb_exactos": 500,
    "top_n": 20,
    "seed": 42,
}

_OBSERVER_ID = "tools.datasources.file_observer:factory"


class FileObserver:
    """Observer sobre un archivo local (CSV/Parquet vía `ds_profile`).

    `options`:
      - `path` (str, obligatorio): ruta REPO-RELATIVA al archivo.
      - `max_filas_exactas`/`max_mb_exactos`/`top_n`/`seed` (opcionales):
        kwargs de `ds_profile.report.generar_perfil`, con sus mismos
        defaults si no vienen.
      - `_repo_root` (opcional, solo si se construyó vía `factory` directa):
        ver docstring del módulo.
    """

    def __init__(self, source_id: str, options: dict, repo_root: Optional[Any] = None) -> None:
        self.source_id = source_id
        self.options = dict(options or {})
        self._repo_root = repo_root if repo_root is not None else self.options.get("_repo_root")

    def capabilities(self) -> dict:
        """Todo lo que `ds_profile` puede producir (R10): facetas de dataset
        `schema`/`row_count`/`fingerprint` (sin `snapshot`: `ds_profile` no
        tiene noción de corte/snapshot); facetas de campo, todas con
        `{"exact", "approximate"}` como conjunto soportado (depende de si el
        perfil corrió en modo muestreado). `operations = ["read"]`."""
        facets = {faceta: ["exact"] for faceta in _DATASET_FACETS_SOPORTADAS}
        for faceta in _FIELD_FACETS_SOPORTADAS:
            facets[faceta] = ["exact", "approximate"]
        return {"facets": facets, "operations": ["read"]}

    def observe(self, request: dict) -> dict:
        """Corre `ds_profile.report.generar_perfil` sobre `options['path']`
        (tras el guard de holdout) y devuelve `profile_to_observation(...)
        .to_dict()` con `provenance` reemplazada por los datos reales de este
        observer. La ruta nunca aparece en el resultado."""
        if self._repo_root is None:
            raise RuntimeError(
                "FileObserver.observe: falta repo_root. Construí el observer con "
                "file_observer.factory_with_repo_root(repo_root)(source_id, options) "
                "(recomendado) o incluí la clave interna '_repo_root' en options."
            )
        repo_root = Path(self._repo_root)

        ruta_relativa = self.options.get("path")
        if not isinstance(ruta_relativa, str) or not ruta_relativa:
            raise RuntimeError("FileObserver.observe: options['path'] es obligatorio (str, ruta repo-relativa).")

        try:
            from ds_profile import report as ds_report
            from ds_profile import holdout_guard as ds_holdout_guard
        except ImportError as exc:
            raise RuntimeError(
                "FileObserver.observe: falta el paquete 'ds_profile'. "
                "Corré 'ds_init sync --stage experiment' para instalarlo."
            ) from exc

        ruta_absoluta_local = repo_root / ruta_relativa

        permitido, _motivo = ds_holdout_guard.verificar_permitido(ruta_absoluta_local, repo_root)
        if not permitido:
            # El motivo de `verificar_permitido` puede incluir la ruta
            # absoluta local (p. ej. caso "no resoluble"): no se propaga acá,
            # solo la ruta repo-relativa que ya conocíamos.
            raise RuntimeError(
                f"FileObserver.observe: acceso denegado por guard de holdout a la ruta "
                f"repo-relativa '{ruta_relativa}'."
            )

        kwargs_perfil = dict(_DEFAULTS_GENERAR_PERFIL)
        for clave in kwargs_perfil:
            if clave in self.options:
                kwargs_perfil[clave] = self.options[clave]

        # `generar_perfil` siempre escribe `profile.json` a disco (no hay
        # modo "sin persistir" en su firma real, ver `report.py:234-237`):
        # se usa un directorio temporal que se borra al salir del `with`,
        # para no dejar ningún perfil crudo persistido en el repo del
        # proyecto (lo único que persiste luego es la observación
        # normalizada, responsabilidad de `runtime.py`).
        with tempfile.TemporaryDirectory() as directorio_temporal:
            resultado = ds_report.generar_perfil(
                ruta_input=ruta_absoluta_local,
                output_dir=Path(directorio_temporal),
                incluir_markdown=False,
                **kwargs_perfil,
            )
            perfil = resultado["perfil"]

        observacion = profile_bridge.profile_to_observation(perfil, self.source_id)

        from . import core as datasources_core

        provenance_real = datasources_core.SourceProvenance(
            source_id=self.source_id,
            observer_id=_OBSERVER_ID,
            observer_code_sha256=None,
            access_mode="read",
            source_kind="file",
            generated_at=profile_bridge._ahora_utc_iso(),
            tool_versions={"ds_profile": getattr(ds_report, "TOOL_VERSION", "")},
            requested_facets=tuple((request or {}).get("facets", ())) if isinstance(request, dict) else (),
            unsupported_facets=(),
        )

        observacion_final = datasources_core.SourceObservation(
            source_id=self.source_id,
            provenance=provenance_real,
            dataset=observacion.dataset,
            fields=observacion.fields,
            omitted_facets=observacion.omitted_facets,
            schema_version=observacion.schema_version,
        )

        return observacion_final.to_dict()


def factory(source_id: str, options: dict):
    """`factory(source_id, options) -> FileObserver`, firma exacta pedida por
    R15/R28. Toma `repo_root` de `options['_repo_root']` si está presente
    (ver docstring del módulo); si falta, `observe()` falla con
    `RuntimeError` claro en vez de asumir un directorio. Para composición
    real se recomienda `factory_with_repo_root` en su lugar."""
    return FileObserver(source_id, options)


def factory_with_repo_root(repo_root: Any):
    """Fábrica de más alto nivel -- **RECOMENDADA**. Devuelve un
    `factory(source_id, options)` normal (closure) ya atado a `repo_root`,
    sin necesidad de inyectar una clave privada en `options`."""

    def _factory(source_id: str, options: dict):
        return FileObserver(source_id, options, repo_root=repo_root)

    return _factory
