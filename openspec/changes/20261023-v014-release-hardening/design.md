# Diseño — 20261023-v014-release-hardening

Mismo patrón que v0.11–v0.13: marcadores → notas → inventario → smoke y dogfood → baseline una sola vez (último cambio a managed) → regresión completa serial por batches con ledger → install/upgrade/Doctor → privacidad → verification.md → commit de release. El writer entrega marcadores, notas, inventario, smoke, dogfood y CI; el Lead ejecuta regresión, baseline, install/upgrade, Doctor y barridos.
