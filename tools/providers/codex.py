"""Adapter fino de Codex CLI (v0.5 Change 0). No verificado contra la CLI
real en este entorno (`codex` ausente de PATH al momento de escribir este
adapter) -- detección e invocación siguen el mismo patrón estructural que
`claude_code.py`, pero el comando de invocación es best-effort."""
from __future__ import annotations

import shutil
import subprocess
import time
from typing import Optional

from tools.providers.core import (
    InvocationRequest,
    InvocationResult,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderInfo,
    classify_availability_error,
)


class CodexAdapter(ProviderAdapter):
    provider_id = "codex"
    cli_command = "codex"
    display_name = "Codex CLI"

    def detect(self) -> ProviderInfo:
        ruta = shutil.which(self.cli_command)
        # tool_use=True es razonable de inferir (Codex CLI es un agente de
        # código); el resto queda en False por no estar verificado en este
        # entorno.
        capabilities = ProviderCapabilities(
            streaming=False, tool_use=True, thinking_effort=False, handoff=False
        )
        if ruta is None:
            return ProviderInfo(
                provider_id=self.provider_id,
                display_name=self.display_name,
                cli_command=self.cli_command,
                available=False,
                authenticated=None,
                version=None,
                capabilities=capabilities,
                detail=f"CLI '{self.cli_command}' no encontrada en PATH",
            )

        version: Optional[str] = None
        try:
            resultado = subprocess.run(
                [self.cli_command, "--version"], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ProviderInfo(
                provider_id=self.provider_id,
                display_name=self.display_name,
                cli_command=self.cli_command,
                available=False,
                authenticated=None,
                version=None,
                capabilities=capabilities,
                detail=f"no se pudo ejecutar '{self.cli_command} --version': {exc}",
            )

        if resultado.returncode == 0:
            primera_linea = resultado.stdout.strip().splitlines()
            version = primera_linea[0].strip() if primera_linea else None
            return ProviderInfo(
                provider_id=self.provider_id,
                display_name=self.display_name,
                cli_command=self.cli_command,
                available=True,
                authenticated=None,
                version=version,
                capabilities=capabilities,
                detail=f"CLI encontrada en {ruta}",
            )

        return ProviderInfo(
            provider_id=self.provider_id,
            display_name=self.display_name,
            cli_command=self.cli_command,
            available=False,
            authenticated=None,
            version=None,
            capabilities=capabilities,
            detail=f"'{self.cli_command} --version' terminó con código {resultado.returncode}",
        )

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        if shutil.which(self.cli_command) is None:
            return InvocationResult(
                provider_id=self.provider_id,
                exit_code=127,
                stdout="",
                stderr=f"CLI '{self.cli_command}' no encontrada en PATH",
                ok=False,
                availability_error="unavailable",
                duration_s=0.0,
            )

        # Codex CLI expone un modo no interactivo `codex exec` -- no
        # verificado en este entorno por ausencia de la CLI.
        cmd = [self.cli_command, "exec", request.prompt]
        cmd += list(request.extra_args)

        inicio = time.monotonic()
        try:
            resultado = subprocess.run(
                cmd, capture_output=True, text=True, cwd=request.cwd, timeout=request.timeout_s
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return InvocationResult(
                provider_id=self.provider_id,
                exit_code=-1,
                stdout="",
                stderr=f"fallo al invocar '{self.cli_command}': {exc}",
                ok=False,
                availability_error="unavailable",
                duration_s=time.monotonic() - inicio,
            )
        duracion = time.monotonic() - inicio

        exit_code = resultado.returncode
        return InvocationResult(
            provider_id=self.provider_id,
            exit_code=exit_code,
            stdout=resultado.stdout,
            stderr=resultado.stderr,
            ok=(exit_code == 0),
            availability_error=classify_availability_error(exit_code, resultado.stderr)
            if exit_code != 0
            else None,
            duration_s=duracion,
        )
