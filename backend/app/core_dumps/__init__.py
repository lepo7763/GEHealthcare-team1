"""Core dump collection from the platform node.

The Axone OS kernel pipes cores to ``/axone/bin/coredump_handler.sh``, which
writes them flat into ``/var/log/files`` on the host. The per-app
``*-coredump-pvc`` volumes (also under ``/var/log/files/pvc-*``) are collected
too, but on the lab cluster they are all empty.
"""
