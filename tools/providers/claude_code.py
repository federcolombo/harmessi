"""Adapter fino de Claude Code (v0.5 Change 0). Único de los 4 adapters con
detección e invocación verificadas contra la CLI real en este entorno
(`claude` en PATH, versión `2.1.274`, `claude --help` expone `--effort
<level>` con valores `low,medium,high,xhigh,max`)."""
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


class ClaudeCodeAdapter(ProviderAdapter):
    provider_id = "claude_code"
    cli_command = "claude"
    display_name = "Claude Code"

    def detect(self) -> ProviderInfo:
        ruta = shutil.which(self.cli_command)
        capabilities = ProviderCapabilities(
            streaming=True, tool_use=True, thinking_effort=True, handoff=True
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
                # No hay forma limpia y barata de verificar autenticación sin
                # invocar una sesión real -- limitación documentada, no se
                # inventa una señal.
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

        cmd = [self.cli_command, "-p", request.prompt, "--output-format", "json"]
        if request.model:
            cmd += ["--model", request.model]
        if request.effort:
            cmd += ["--effort", request.effort]
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
