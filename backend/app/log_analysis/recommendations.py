import re
from typing import Optional

from .schemas import Recommendation

# Known error signatures -> what a field engineer should do next.
# Checked in order and the FIRST match wins, so specific causes come before generic ones
# (e.g. "leaderelection lost" before the generic timeout rule, which would also match its
# "context deadline exceeded" lines).
RULES = [
    (
        re.compile(r"leaderelection lost|lost leader|etcd.*(timeout|unavailable)", re.I),
        Recommendation(
            title="Lost etcd leadership",
            action="k3s restarts when etcd answers too slowly, usually from slow or full disk. "
            "Check free space (df -h) and disk I/O on the node, and look for etcd "
            "'apply request took too long' warnings.",
        ),
    ),
    (
        re.compile(r"no space left on device|disk ?pressure", re.I),
        Recommendation(
            title="Disk full",
            action="Free up disk space on the node or expand storage, then check the node "
            "for the DiskPressure condition (kubectl describe node).",
        ),
    ),
    (
        re.compile(r"out ?of ?memory|OOMKilled|\bOOM\b", re.I),
        Recommendation(
            title="Out of memory",
            action="The container hit its memory limit. Compare usage with the limit "
            "(kubectl top pod) and raise the limit or report the leak to engineering.",
        ),
    ),
    (
        re.compile(r"CrashLoopBackOff|back-off restarting", re.I),
        Recommendation(
            title="Container keeps crashing",
            action="Open the container's _previous.log in the package: it holds the output "
            "from just before the last crash.",
        ),
    ),
    (
        re.compile(r"ImagePullBackOff|ErrImagePull", re.I),
        Recommendation(
            title="Image can't be pulled",
            action="The lab has no internet access, so images must already be on the node. "
            "Check the image name and tag and that it was preloaded.",
        ),
    ),
    (
        re.compile(r"x509|certificate|unauthori[sz]ed|forbidden|permission denied|\b40[13]\b", re.I),
        Recommendation(
            title="Authentication or certificate problem",
            action="Check the kubeconfig credentials and certificate expiry, and that the "
            "service account has the needed permissions.",
        ),
    ),
    (
        re.compile(
            r"connection refused|no route to host|connection is not available|"
            r"connection reset|could not connect|unreachable",
            re.I,
        ),
        Recommendation(
            title="Can't reach a dependency",
            action="Check that the target pod is Running and Ready and that its Service name "
            "and port are correct (kubectl get pods,svc -A).",
        ),
    ),
    (
        re.compile(r"timed? ?out|timeout|deadline exceeded", re.I),
        Recommendation(
            title="Request timed out",
            action="The other side is slow or overloaded. Check node load (kubectl top nodes) "
            "and whether the target service is healthy.",
        ),
    ),
    (
        re.compile(r"Exception|Traceback|panic:|NullPointer", re.I),
        Recommendation(
            title="Application error",
            action="Likely a bug or unexpected input. Send this package to engineering with "
            "the stack trace; there is no field fix.",
        ),
    ),
]


def recommend_action(message: str) -> Optional[Recommendation]:
    """Returns the suggested next step for an error line, or None if no rule matches."""
    for pattern, recommendation in RULES:
        if pattern.search(message):
            return recommendation
    return None
