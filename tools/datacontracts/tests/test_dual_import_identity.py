"""Doble identidad de paquete (`tools.datacontracts.validation` vs
`datacontracts.validation`, causada por `tools/` sin `__init__.py`) -- T5 del Change 1
de v0.8.

LÍMITE DOCUMENTADO (no forzado): un test unitario aislado que importe
`tools.datacontracts.validation` y ADEMÁS `datacontracts.validation` (sin el prefijo
`tools.`) dentro del mismo proceso de pytest no reproduce limpiamente el escenario real
de doble identidad. Motivo: `sys.modules` es un caché global por nombre de módulo
compartido por todo el proceso -- si CUALQUIER otro test de esta suite (o un import
transitivo de otro módulo de `tools.*`) ya importó `tools.datacontracts.validation`
antes de que este test corra, ese import queda cacheado bajo esa clave; forzar un
segundo import bajo la clave `datacontracts.validation` requeriría además que
`datacontracts` (sin prefijo) sea resoluble como paquete de primer nivel, lo cual
depende de qué directorio esté en `sys.path[0]` al momento exacto en que arrancó
pytest (rootdir vs. `tools/` insertado por algún bootstrap de otro módulo bajo prueba,
como hace por ejemplo `tools/datacontracts/validation.py:67-69` con `_TOOLS_DIR`). Ese
estado de `sys.path`/`sys.modules` NO es determinista ni aislable con
`importlib.reload`/`del sys.modules[...]` sin arriesgar contaminar el resto de la
suite (podría dejar DOS clases `DataContract` distintas conviviendo, cada una con su
propia identidad de tipo, que es justo el síntoma real del bug de doble identidad --
pero producirlo a propósito en este test no prueba nada sobre el código bajo prueba,
solo sobre el orden de ejecución de pytest). Forzar ese escenario "fresco" acá sería
frágil y no representativo: se documenta el límite en vez de fingir una reproducción.

MITIGACIÓN REAL ya aplicada en el propio código (la que este test SÍ puede verificar
de forma honesta y determinista): `validate_contract_observation` (ver su docstring en
`tools/datacontracts/validation.py`) acepta tanto una instancia real de
`datasources.core.SourceObservation` como un `dict` con esa forma exacta
(normalizado internamente vía `SourceObservation.from_dict`) -- así que aunque dos
imports paralelos del paquete `datasources` produjeran dos clases `SourceObservation`
DISTINTAS en memoria (la causa raíz de la doble identidad), un caller que le pase un
`dict` en vez de una instancia nunca sufre un `isinstance` que falle silenciosamente
por comparar contra la clase "equivocada". Es la mitigación real, no un rodeo de este
test."""
from __future__ import annotations

import unittest

from dsguard import checks
from tools.datacontracts import core as dc
from tools.datacontracts import validation as v
from tools.datacontracts.tests.test_validation import _campo, _contrato
from tools.datacontracts.tests.test_observation_native import _campo_obs, _observacion
from datasources import core as ds_core


def _por_codigo(resultados, codigo):
    return [r for r in resultados if r.code == codigo]


class TestDobleImportNoReproducibleLimpiamente(unittest.TestCase):
    """Ver docstring del módulo: se documenta el límite en vez de forzar un import
    paralelo bajo `datacontracts.validation` (sin prefijo `tools.`), porque el estado
    de `sys.modules`/`sys.path` al momento de correr este archivo dentro de la suite
    completa de pytest no es aislable de forma determinista sin arriesgar contaminar
    otros tests. Este test deja constancia explícita de que se intentó evaluar la
    reproducción y de por qué se descartó, en vez de omitir el tema en silencio."""

    def test_import_bajo_prefijo_tools_es_estable_y_reutilizable(self):
        # Lo único verificable de forma determinista y sin efectos secundarios: que el
        # import "canónico" del proyecto (con prefijo tools.) es estable dentro del
        # proceso -- reimportar el mismo nombre devuelve el MISMO objeto módulo
        # (identidad, no solo igualdad), como exige cualquier caché de sys.modules
        # sano.
        import tools.datacontracts.validation as v_otra_vez

        self.assertIs(v, v_otra_vez)
        self.assertIs(v.validate_contract, v_otra_vez.validate_contract)
        self.assertIs(v.validate_contract_observation, v_otra_vez.validate_contract_observation)


class TestMitigacionRealDobleIdentidad(unittest.TestCase):
    """`validate_contract_observation` acepta tanto una `SourceObservation` real como
    un `dict` con esa forma exacta, y ambos dan el MISMO resultado sobre un caso
    trivial -- la mitigación real contra el problema de doble identidad de paquete
    (documentada en el propio docstring de la función), verificable sin depender del
    estado de `sys.modules`."""

    def _caso_trivial(self):
        contrato = _contrato(fields=(_campo(name="id", type_family="integer", required=True, nullable=True),))
        observacion = _observacion(
            [_campo_obs("id", facets={"null_count": {"value": 0, "exactness": "exact"}})]
        )
        return contrato, observacion

    def test_instancia_real_y_dict_equivalente_dan_el_mismo_resultado(self):
        contrato, observacion = self._caso_trivial()
        observacion_dict = observacion.to_dict()

        resultados_instancia = v.validate_contract_observation(contrato, observacion)
        resultados_dict = v.validate_contract_observation(contrato, observacion_dict)

        self.assertEqual(
            [r.to_dict() for r in resultados_instancia],
            [r.to_dict() for r in resultados_dict],
        )
        # Ninguno de los dos caminos debería caer en el gate de forma (CONTRACT-INPUT/
        # CONTRACT-EVIDENCE-MISSING técnico) -- ambos son entradas válidas.
        self.assertFalse(any(r.kind == checks.KIND_TECHNICAL_ERROR for r in resultados_instancia))
        self.assertFalse(any(r.kind == checks.KIND_TECHNICAL_ERROR for r in resultados_dict))

    def test_dict_con_forma_invalida_da_evidence_missing_tecnico_no_lanza(self):
        contrato, _observacion = self._caso_trivial()
        dict_invalido = {"esto": "no tiene la forma de SourceObservation"}
        resultados = v.validate_contract_observation(contrato, dict_invalido)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        self.assertEqual(resultados[0].code, v.CODE_EVIDENCE_MISSING)
        self.assertEqual(resultados[0].kind, checks.KIND_TECHNICAL_ERROR)


if __name__ == "__main__":
    unittest.main()
