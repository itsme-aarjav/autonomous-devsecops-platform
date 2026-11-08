"""
Autonomous AIOps Platform — Ansible Automated Self-Healing Runbook Executor
"""

import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel


class AnsibleExecutionResult(BaseModel):
    """Result of an Ansible runbook execution."""

    success: bool
    playbook: str
    workload: str
    returncode: int
    stdout: str
    stderr: str = ""
    summary: str = ""


class AnsibleRunbookExecutor:
    """
    Executes automated self-healing Ansible playbooks for operational incidents.
    Supports both live execution via `ansible-playbook` and offline / simulated execution.
    """

    def __init__(
        self,
        playbooks_dir: Optional[str] = None,
        inventory_file: Optional[str] = None,
        dry_run: bool = False,
    ):
        base_dir = Path(__file__).resolve().parents[3]  # repo root
        self.playbooks_dir = Path(playbooks_dir).resolve() if playbooks_dir else (base_dir / "devops" / "ansible" / "playbooks")
        self.inventory_file = Path(inventory_file).resolve() if inventory_file else (base_dir / "devops" / "ansible" / "inventory.ini")
        self.dry_run = dry_run or os.getenv("ANSIBLE_DRY_RUN", "false").lower() in ("true", "1", "yes")

    def execute_runbook(
        self,
        playbook_name: str,
        workload: str,
        namespace: str = "boutique",
        extra_vars: Optional[Dict[str, Any]] = None,
    ) -> AnsibleExecutionResult:
        """
        Executes a targeted self-healing playbook with the specified workload parameters.
        """
        playbook_path = self.playbooks_dir / playbook_name
        if not playbook_path.is_file():
            return AnsibleExecutionResult(
                success=False,
                playbook=playbook_name,
                workload=workload,
                returncode=1,
                stdout="",
                stderr=f"Playbook file not found: {playbook_path}",
                summary=f"Execution failed: playbook '{playbook_name}' does not exist.",
            )

        merged_vars = {
            "workload": workload,
            "namespace": namespace,
        }
        if extra_vars:
            merged_vars.update(extra_vars)

        # Explicit dry-run / simulation mode
        if self.dry_run:
            summary = (
                f"[SIMULATED] Ansible self-healing executed successfully for {workload} "
                f"using playbook '{playbook_name}' (vars: {merged_vars})"
            )
            return AnsibleExecutionResult(
                success=True,
                playbook=playbook_name,
                workload=workload,
                returncode=0,
                stdout=summary,
                stderr="",
                summary=summary,
            )

        # Live execution: strictly verify required command-line tools are available
        ansible_bin = shutil.which("ansible-playbook")
        if not ansible_bin:
            return AnsibleExecutionResult(
                success=False,
                playbook=playbook_name,
                workload=workload,
                returncode=127,
                stdout="",
                stderr="Executable 'ansible-playbook' not found in PATH.",
                summary=f"Execution failed: 'ansible-playbook' CLI is not installed or available in PATH.",
            )

        kubectl_bin = shutil.which("kubectl")
        if not kubectl_bin:
            return AnsibleExecutionResult(
                success=False,
                playbook=playbook_name,
                workload=workload,
                returncode=127,
                stdout="",
                stderr="Executable 'kubectl' not found in PATH.",
                summary=f"Execution failed: 'kubectl' CLI is required for Kubernetes playbooks but not found in PATH.",
            )

        cmd = [
            ansible_bin,
            str(playbook_path),
            "-i",
            str(self.inventory_file),
            "--extra-vars",
            json.dumps(merged_vars),
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            success = (proc.returncode == 0)
            summary = (
                f"Ansible playbook '{playbook_name}' completed with status {proc.returncode} for {workload}."
                if success
                else f"Ansible playbook '{playbook_name}' failed with status {proc.returncode} for {workload}."
            )
            return AnsibleExecutionResult(
                success=success,
                playbook=playbook_name,
                workload=workload,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                summary=summary,
            )
        except Exception as e:
            return AnsibleExecutionResult(
                success=False,
                playbook=playbook_name,
                workload=workload,
                returncode=-1,
                stdout="",
                stderr=str(e),
                summary=f"Ansible runbook execution raised exception: {str(e)}",
            )
