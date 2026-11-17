"""Privileged collector Job that reads the node's firewall state.

firewall-cmd talks to the host's firewalld over the host's D-Bus, and
iptables/nft read the host network namespace, so the commands run from the
host's own mount + network + PID namespaces via ``nsenter -t 1``. That needs a
privileged pod with hostPID. The commands are a fixed read-only list
(parsing.COMMANDS); nothing from the request reaches them.
"""

from __future__ import annotations

import io
import secrets
import tarfile
import time
import uuid
from typing import Callable, Dict, List, Tuple

from kubernetes import client

from app.core.job_exec import JobExecError, JobExecSession

from .config import FirewallConfig
from .parsing import build_script, parse_framed

CONTAINER_NAME = "collector"
_HOST_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_CONFIG_TAR_LIMIT = 16 * 1024 * 1024


class FirewallCollectionError(JobExecError):
    """The firewall collector Job could not be run or its commands failed."""


def build_firewall_job(config: FirewallConfig) -> client.V1Job:
    labels = {"app": config.job_prefix}
    container = client.V1Container(
        name=CONTAINER_NAME,
        image=config.image,
        image_pull_policy=config.image_pull_policy,
        command=["sleep", str(config.job_deadline_seconds)],
        # firewall-cmd (python) runs inside this container's cgroup even after
        # nsenter, so the memory limit has to fit it.
        resources=client.V1ResourceRequirements(
            requests={"cpu": "50m", "memory": "64Mi"},
            limits={"cpu": "500m", "memory": "256Mi"},
        ),
        security_context=client.V1SecurityContext(
            privileged=True,  # required to nsenter PID 1's mount namespace
            run_as_user=0,
            read_only_root_filesystem=True,
        ),
    )
    pod_spec = client.V1PodSpec(
        restart_policy="Never",
        node_name=config.node_name,
        host_pid=True,
        automount_service_account_token=False,
        enable_service_links=False,
        termination_grace_period_seconds=0,
        containers=[container],
    )
    return client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name=f"{config.job_prefix}-{uuid.uuid4().hex[:8]}",
            namespace=config.namespace,
            labels=labels,
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            active_deadline_seconds=config.job_deadline_seconds,
            ttl_seconds_after_finished=config.job_ttl_seconds,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels), spec=pod_spec
            ),
        ),
    )


class FirewallSession(JobExecSession):
    def __init__(
        self,
        core: client.CoreV1Api,
        batch: client.BatchV1Api,
        config: FirewallConfig,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(
            core,
            batch,
            build_firewall_job(config),
            CONTAINER_NAME,
            startup_timeout_seconds=config.startup_timeout_seconds,
            poll_interval_seconds=config.poll_interval_seconds,
            sleep=sleep,
            error_cls=FirewallCollectionError,
        )
        self.config = config

    def run_commands(self) -> Dict[str, Tuple[str, int]]:
        """Run every command in one exec on the host; {id: (output, exit code)}."""
        token = f"@@FW-{secrets.token_hex(8)}@@"
        script = f"export PATH={_HOST_PATH}\nexport LC_ALL=C\n" + build_script()
        command: List[str] = [
            "nsenter", "-t", "1", "-m", "-n", "-p", "--",
            "sh", "-c", script, "sh", token,
        ]
        output = self.exec_text(command, self.config.commands_timeout_seconds)
        results = parse_framed(output, token)
        if not results:
            raise FirewallCollectionError(
                "Firewall commands produced no output (nsenter into the host failed?)"
            )
        return results

    def config_files(self) -> Dict[str, bytes]:
        """Regular files under the host's /etc/firewalld: {relative path: bytes}.

        Read through /proc/1/root with the container's own tar, so it doesn't
        depend on tar being installed on the host.
        """
        buffer = io.BytesIO()
        self.exec(
            ["tar", "-C", "/proc/1/root/etc", "-cf", "-", "firewalld"],
            buffer,
            60,
            limit_bytes=_CONFIG_TAR_LIMIT,
        )
        buffer.seek(0)
        files: Dict[str, bytes] = {}
        try:
            with tarfile.open(fileobj=buffer, mode="r:") as tar:
                for member in tar:
                    name = member.name.lstrip("./")
                    if not member.isreg() or ".." in name.split("/"):
                        continue
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        files[name] = extracted.read()
        except tarfile.TarError as e:
            raise FirewallCollectionError(f"Could not read /etc/firewalld archive: {e}")
        return files
