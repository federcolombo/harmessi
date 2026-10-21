"""Tests de la primitiva de deprecación (v0.13 Change 5, R9-R11)."""
from __future__ import annotations

import dataclasses
import warnings

import pytest

from tools.harmessi import deprecation
from tools.harmessi.deprecation import DEPRECATIONS, Deprecation, advertir, validar_registro


def _valida(**cambios) -> Deprecation:
    base = dict(nombre="flag --viejo", tipo="flag", desde="0.13.0", reemplazo="--nuevo", remocion_minima="0.14.0")
    base.update(cambios)
    return Deprecation(**base)


def test_registro_v013_vacio_y_valido():
    assert DEPRECATIONS == ()
    assert validar_registro(DEPRECATIONS) == []


def test_dataclass_congelada():
    entrada = _valida()
    with pytest.raises(dataclasses.FrozenInstanceError):
        entrada.nombre = "otro"


def test_entrada_valida_sin_problemas():
    assert validar_registro([_valida()]) == []
    assert validar_registro([_valida(desde="1.2.0", remocion_minima="2.0.0")]) == []


@pytest.mark.parametrize("campo", ["desde", "remocion_minima"])
@pytest.mark.parametrize("valor", ["0.13", "v0.13.0", "0.13.0-rc1", "", "a.b.c", "01.2.3"])
def test_version_no_semver(campo, valor):
    problemas = validar_registro([_valida(**{campo: valor})])
    assert problemas and any(campo in p for p in problemas)


def test_remocion_no_posterior():
    assert validar_registro([_valida(remocion_minima="0.13.0")])
    assert validar_registro([_valida(remocion_minima="0.12.9")])


def test_en_0x_exige_una_menor_posterior():
    assert validar_registro([_valida(remocion_minima="0.13.5")])
    assert validar_registro([_valida(remocion_minima="0.14.0")]) == []
    assert validar_registro([_valida(remocion_minima="1.0.0")]) == []


def test_en_1x_exige_la_siguiente_mayor():
    assert validar_registro([_valida(desde="1.2.0", remocion_minima="1.3.0")])
    assert validar_registro([_valida(desde="1.2.0", remocion_minima="1.99.0")])
    assert validar_registro([_valida(desde="1.2.0", remocion_minima="2.0.0")]) == []
    assert validar_registro([_valida(desde="1.2.0", remocion_minima="3.1.0")]) == []


@pytest.mark.parametrize("valor", ["0.13.0\n", " 0.13.0", "0.13.0 ", "0.13.٣"])
def test_semver_estricto_sin_saltos_ni_unicode(valor):
    assert validar_registro([_valida(desde=valor)])
    assert validar_registro([_valida(remocion_minima=valor.replace("0.13", "0.14"))])


def test_nombres_duplicados_se_normalizan():
    problemas = validar_registro([_valida(nombre="x"), _valida(nombre=" x ")])
    assert any("duplicado" in p for p in problemas)


@pytest.mark.parametrize(
    "campos",
    [
        {"nombre": None},
        {"nombre": ["lista"]},
        {"tipo": ["lista"]},
        {"tipo": None},
        {"reemplazo": None},
        {"desde": None},
        {"remocion_minima": ["0.14.0"]},
        {"desde": 13},
    ],
)
def test_valores_inesperados_se_reportan_sin_lanzar(campos):
    assert validar_registro([_valida(**campos)])


def test_registro_no_iterable_no_lanza():
    assert validar_registro(None)
    assert validar_registro(5)


def test_advertir_rechaza_entrada_invalida():
    with warnings.catch_warnings(record=True) as capturadas:
        warnings.simplefilter("always")
        with pytest.raises(ValueError):
            advertir("flag --viejo", (_valida(reemplazo=""),))
    assert capturadas == []


def test_reemplazo_vacio():
    assert validar_registro([_valida(reemplazo="  ")])


def test_tipo_invalido():
    assert validar_registro([_valida(tipo="otro")])
    for tipo in ("cli", "flag", "schema-field", "skill-key", "api"):
        assert validar_registro([_valida(tipo=tipo)]) == []


def test_nombres_duplicados():
    problemas = validar_registro([_valida(), _valida()])
    assert any("duplicado" in p for p in problemas)


def test_entrada_que_no_es_deprecation():
    assert validar_registro(["x"])


def test_advertir_formato_fijo():
    registro = (_valida(),)
    with warnings.catch_warnings(record=True) as capturadas:
        warnings.simplefilter("always")
        advertir("flag --viejo", registro)
    assert len(capturadas) == 1
    assert issubclass(capturadas[0].category, DeprecationWarning)
    assert str(capturadas[0].message) == (
        "flag --viejo está deprecado desde 0.13.0; usar --nuevo; se removerá no antes de 0.14.0"
    )


def test_advertir_nombre_no_registrado_falla():
    with pytest.raises(KeyError):
        advertir("no-existe")
    with pytest.raises(KeyError):
        advertir("flag --viejo", ())


def test_sin_decoradores_ni_estado_global():
    assert not hasattr(deprecation, "deprecado")
    assert isinstance(deprecation.DEPRECATIONS, tuple)
