"""Collector Job for the Prometheus TSDB.

Reuses the core-dump collector: the same locked-down Job (read-only hostPath
mount, no API token) and the same exec-based sha256sum/cat transfer, pointed at
the directory that holds Prometheus's data.
"""

from __future__ import annotations

import time
from typing import Callable, List

from kubernetes import client

from app.core.job_exec import JobExecError
from app.core_dumps.collector import CollectorSession

from .config import PrometheusConfig
from .parsing import LISTING_SCRIPT, parse_listing
from .schemas import TsdbDataDir


class PrometheusCollectionError(JobExecError):
    """The collector Job could not be run or a transfer failed."""


class PrometheusSession(CollectorSession):
    def __init__(
        self,
        core: client.CoreV1Api,
        batch: client.BatchV1Api,
        config: PrometheusConfig,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(
            core, batch, config, sleep=sleep, error_cls=PrometheusCollectionError
        )

    def list_data_dirs(self) -> List[TsdbDataDir]:
        output = self.exec_text(
            self._in_core_dir(LISTING_SCRIPT, str(self.config.search_depth)),
            timeout_seconds=300,
        )
        return parse_listing(output)
