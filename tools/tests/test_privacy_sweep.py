"""Barrido de privacidad de artefactos publicables (B-20).

AVISO: el barrido es determinista pero HEURISTICO. No garantiza deteccion
perfecta: busca rutas personales, emails reales, secretos obvios y el
username del autor mediante expresiones regulares. Una ausencia de hallazgos
no prueba que no haya datos sensibles.

Alcance de `escanear_repo`: tools/tests/fixtures/**, docs/** (recursivo,
incluye docs/roadmap), ARCHITECTURE.md, README.md y las suites/casos .json de
tools/harmessi_bench (suites/ y scenarios/). Este archivo vive en tools/tests
(fuera del alcance) y ademas arma sus ejemplos por concatenacion.
"""
import re
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
MAX_FRAGMENTO = 40

# Entradas: {ruta_relativa_posix: (patron, motivo)}. Motivo obligatorio.
WHITELIST = {}

SUFIJOS_TEXTO = {".json", ".md", ".txt", ".py", ".yml", ".yaml", ".toml", ".csv"}

NOMBRES_GENERICOS = {
    "user", "users", "usuario", "nombre", "name", "example", "ejemplo",
    "tu_usuario", "runner", "username", "you", "me", "foo", "xxx",
}

_NOMBRE = r"([^\\/\s\"'<>{}%$:*?|`()\[\]]+)"
RE_RUTA_WIN = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+" + _NOMBRE)
# Sin "/" final obligatorio (matchea `/home/jperez` al final de linea). El
# lookbehind evita falsos positivos como `tools/Users/x` o `docs/home/readme`.
RE_RUTA_UNIX = re.compile(r"(?<![\w.~/\\-])/(?:home|Users)/" + _NOMBRE)
RE_EMAIL = re.compile(
    r"[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})")
RE_SECRETOS = [
    ("secreto_aws", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("secreto_github", re.compile(r"ghp_[A-Za-z0-9]{30,}")),
    ("secreto_sk", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("secreto_clave_privada",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("secreto_slack", re.compile(r"xox[bp]-")),
]
RE_AUTOR = re.compile("fcol" + "ombo", re.IGNORECASE)

DOMINIOS_EXCLUIDOS = {"example.com", "example.org", "example.net"}
EMAILS_EXCLUIDOS = {"noreply@anthropic.com", "noreply@github.com"}


def _es_generico(nombre):
    n = nombre.strip().lower()
    return (not n) or n in NOMBRES_GENERICOS or any(c in n for c in "{<%$")


def _truncar(s):
    return s[:MAX_FRAGMENTO]


def escanear_texto(texto):
    """Devuelve lista de (patron, fragmento_truncado) hallados en `texto`."""
    out = []
    for rx, pat in ((RE_RUTA_WIN, "ruta_personal"), (RE_RUTA_UNIX, "ruta_personal")):
        for m in rx.finditer(texto):
            if not _es_generico(m.group(1)):
                out.append((pat, _truncar(m.group(0))))
    for m in RE_EMAIL.finditer(texto):
        email = m.group(0).lower()
        dom = m.group(1).lower()
        if email in EMAILS_EXCLUIDOS or dom in DOMINIOS_EXCLUIDOS:
            continue
        if dom.endswith((".test", ".invalid", ".localhost", ".example")):
            continue
        out.append(("email_real", _truncar(m.group(0))))
    for nombre, rx in RE_SECRETOS:
        for m in rx.finditer(texto):
            out.append((nombre, _truncar(m.group(0))))
    for m in RE_AUTOR.finditer(texto):
        out.append(("username_autor", _truncar(m.group(0))))
    return out


def _archivos_barrido(raiz):
    raiz = Path(raiz)
    cands = []
    cands += (raiz / "tools" / "tests" / "fixtures").rglob("*")
    cands += (raiz / "docs").rglob("*")
    cands += (raiz / "tools" / "harmessi_bench" / "suites").rglob("*")
    cands += (raiz / "tools" / "harmessi_bench" / "scenarios").rglob("*")
    cands.append(raiz / "README.md")
    cands.append(raiz / "ARCHITECTURE.md")
    vistos = set()
    for p in sorted(set(cands)):
        if not p.is_file() or p.suffix.lower() not in SUFIJOS_TEXTO:
            continue
        rel = p.relative_to(raiz).as_posix()
        if rel in vistos:
            continue
        vistos.add(rel)
        yield rel, p


def escanear_repo(raiz, whitelist=WHITELIST):
    """Devuelve lista de (ruta_relativa, patron, fragmento) fuera de whitelist."""
    hallazgos = []
    for rel, p in _archivos_barrido(raiz):
        datos = p.read_bytes()
        if b"\x00" in datos:
            continue  # binario
        texto = datos.decode("utf-8", errors="replace")
        for patron, frag in escanear_texto(texto):
            permitido = whitelist.get(rel)
            if permitido and permitido[0] == patron:
                continue
            hallazgos.append((rel, patron, frag))
    return hallazgos


class TestPositivos(unittest.TestCase):
    def _patrones(self, texto):
        return {p for p, _ in escanear_texto(texto)}

    def test_ruta_windows_backslash(self):
        s = "C:" + "\\Us" + "ers\\" + "jperez" + "\\Documentos"
        self.assertIn("ruta_personal", self._patrones(s))

    def test_ruta_windows_barra(self):
        s = "d:/Us" + "ers/" + "jperez" + "/x"
        self.assertIn("ruta_personal", self._patrones(s))

    def test_ruta_windows_json_escapada(self):
        s = "C:" + "\\\\Us" + "ers\\\\" + "jperez"
        self.assertIn("ruta_personal", self._patrones(s))

    def test_ruta_unix(self):
        self.assertIn("ruta_personal", self._patrones("/ho" + "me/" + "jperez/x"))
        self.assertIn("ruta_personal", self._patrones("/Us" + "ers/" + "jperez/x"))

    def test_ruta_unix_fin_de_linea(self):
        self.assertIn("ruta_personal", self._patrones("dir: /ho" + "me/" + "jperez"))
        self.assertIn("ruta_personal", self._patrones("/Us" + "ers/" + "jperez"))

    def test_email_real(self):
        s = "contacto: jperez" + "@" + "empresa" + ".com"
        self.assertIn("email_real", self._patrones(s))

    def test_secretos(self):
        casos = {
            "secreto_aws": "AK" + "IA" + "A" * 16,
            "secreto_github": "gh" + "p_" + "a" * 30,
            "secreto_sk": "s" + "k-" + "a" * 20,
            "secreto_clave_privada": "-----BEGIN " + "RSA PRIVATE" + " KEY-----",
            "secreto_slack": "xo" + "xb-" + "123",
        }
        for esperado, s in casos.items():
            with self.subTest(esperado):
                self.assertIn(esperado, self._patrones(s))

    def test_username_autor(self):
        self.assertIn("username_autor", self._patrones("autor " + "fcol" + "ombo"))
        self.assertIn("username_autor", self._patrones("FCOL" + "OMBO"))

    def test_fragmento_truncado(self):
        s = "C:\\Us" + "ers\\" + "a" * 100
        for _, frag in escanear_texto(s):
            self.assertLessEqual(len(frag), MAX_FRAGMENTO)


class TestNegativos(unittest.TestCase):
    def test_placeholders_ruta(self):
        casos = [
            "C:\\Users\\user\\x", "C:\\Users\\usuario\\x", "C:/Users/nombre/x",
            "C:\\Users\\<nombre>\\x", "C:\\Users\\%USERNAME%\\x",
            "C:\\Users\\{usuario}\\x", "/home/runner/work", "/home/tu_usuario/x",
            "/Users/example/x", "/home/ejemplo/x", "/home/$USER/x", "/home/<x>/y",
            "/home/name/x",
        ]
        for s in casos:
            with self.subTest(s):
                self.assertEqual(escanear_texto(s), [])

    def test_emails_excluidos(self):
        casos = [
            "a@example.com", "a@example.org", "a@dominio.test", "a@x.invalid",
            "a@localhost", "noreply@anthropic.com", "noreply@github.com",
            "actions/checkout@v4.1.0",
        ]
        for s in casos:
            with self.subTest(s):
                self.assertEqual(escanear_texto(s), [])

    def test_rutas_unix_con_prefijo_no_son_personales(self):
        for s in ("tools/Us" + "ers/x", "docs/ho" + "me/readme", "tools/Us" + "ers/jperez"):
            with self.subTest(s):
                self.assertEqual(escanear_texto(s), [])

    def test_texto_inocuo(self):
        self.assertEqual(escanear_texto("sk-corto y ghp_corto, tools/Users/x"), [])


class TestRepo(unittest.TestCase):
    def test_repo_sin_hallazgos(self):
        hallazgos = escanear_repo(REPO_ORIGEN)
        detalle = "\n".join(
            f"{r} | {p} | {_truncar(f)}" for r, p, f in hallazgos)
        self.assertEqual(hallazgos, [], "Hallazgos de privacidad:\n" + detalle)

    def test_whitelist_con_motivo_y_archivo_existente(self):
        self.assertIsInstance(WHITELIST, dict)
        for rel, valor in WHITELIST.items():
            with self.subTest(rel):
                self.assertEqual(len(valor), 2)
                patron, motivo = valor
                self.assertTrue(patron)
                self.assertTrue(str(motivo).strip(), "motivo obligatorio")
                self.assertTrue((REPO_ORIGEN / rel).is_file(), "archivo inexistente")

    def test_temporal_con_ruta_personal_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            fx = raiz / "tools" / "tests" / "fixtures"
            fx.mkdir(parents=True)
            ruta = "C:\\Us" + "ers\\" + "jperez" + "\\proyecto"
            (fx / "inyectado.json").write_text(
                '{"ruta": "' + ruta.replace("\\", "\\\\") + '"}', encoding="utf-8")
            (raiz / "README.md").write_text("limpio", encoding="utf-8")
            hallazgos = escanear_repo(raiz)
            self.assertTrue(hallazgos)
            self.assertEqual(hallazgos[0][0], "tools/tests/fixtures/inyectado.json")
            self.assertEqual(hallazgos[0][1], "ruta_personal")

    def _inyectar(self, contenido, rel="docs/roadmap/inyectado.md"):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            destino = raiz / rel
            destino.parent.mkdir(parents=True)
            destino.write_text(contenido, encoding="utf-8")
            return escanear_repo(raiz)

    def test_temporal_con_email_falla(self):
        hallazgos = self._inyectar("mail: jperez" + "@" + "empresa" + ".com")
        self.assertEqual([(h[0], h[1]) for h in hallazgos],
                         [("docs/roadmap/inyectado.md", "email_real")])

    def test_temporal_con_secreto_falla(self):
        hallazgos = self._inyectar("clave " + "AK" + "IA" + "A" * 16,
                                   rel="tools/harmessi_bench/suites/x.json")
        self.assertEqual([(h[0], h[1]) for h in hallazgos],
                         [("tools/harmessi_bench/suites/x.json", "secreto_aws")])

    def test_temporal_con_ruta_unix_en_docs_recursivo_falla(self):
        hallazgos = self._inyectar("ruta /ho" + "me/" + "jperez")
        self.assertEqual([h[1] for h in hallazgos], ["ruta_personal"])

    def test_temporal_limpio_sin_hallazgos(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "README.md").write_text("hola", encoding="utf-8")
            self.assertEqual(escanear_repo(tmp), [])


if __name__ == "__main__":
    unittest.main()
