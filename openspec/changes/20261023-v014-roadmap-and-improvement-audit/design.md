# Diseño — 20261023-v014-roadmap-and-improvement-audit

Documentación únicamente. Las decisiones técnicas D1–D9 viven en `docs/roadmap/v0.14.md` y se refinan en el SDD de cada Change.

Decisión de ubicación (D1): `tools/harmessi_improve/` como paquete stdlib solo-checkout (como `harmessi_bench`), porque depende de él; datos en `.harmessi/improvement/` (Protected, ignorado por Git, no instalado).
