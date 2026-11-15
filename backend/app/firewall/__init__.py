"""Node firewall settings: firewalld zones/policies, iptables/nft/ipset dumps.

The Axone node runs firewalld on the legacy iptables backend; kube-proxy and
the CNI add their own chains to the same tables. A privileged collector Job
enters the host's namespaces (``nsenter -t 1``) and runs only read-only
commands from a fixed list.
"""