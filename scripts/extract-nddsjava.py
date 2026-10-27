#!/usr/bin/env python3
"""Extract nddsjava.jar from the platform RTI runtime image.

This is a build-time helper only.  It talks to the registry's HTTP API
(Harbor in the lab), downloads the image layers, and copies the RTI Java API
JAR out of the filesystem layer.  No Docker daemon or cluster access is needed.

Examples:
    python3 scripts/extract-nddsjava.py \
        --image 192.168.0.3:30003/spectro-images/us-artifactory.apps.ge-healthcare.net/docker-axone-all/axone-umfcompatibilitycheck:uw-badger-latest \
        --output collector/lib/nddsjava.jar

The image is public-read in the lab.  If your registry requires credentials,
pass --username/--password or set REGISTRY_USERNAME/REGISTRY_PASSWORD.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_IMAGE = (
    "192.168.0.3:30003/spectro-images/"
    "us-artifactory.apps.ge-healthcare.net/docker-axone-all/"
    "axone-umfcompatibilitycheck:uw-badger-latest"
)
TARGET_MEMBER = "opt/axone-umfcompatibilitycheck/lib/nddsjava.jar"
MANIFEST_ACCEPT = ", ".join(
    [
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.index.v1+json",
    ]
)


class RegistryError(RuntimeError):
    pass


class RegistryClient:
    def __init__(
        self,
        registry: str,
        username: str | None = None,
        password: str | None = None,
        verify_tls: bool = False,
        timeout: float = 60.0,
    ) -> None:
        self.registry = registry
        self.username = username
        self.password = password
        self.timeout = timeout
        self.context = ssl.create_default_context()
        if not verify_tls:
            self.context.check_hostname = False
            self.context.verify_mode = ssl.CERT_NONE
        self.token: str | None = None

    @property
    def base_url(self) -> str:
        return f"https://{self.registry}"

    def _auth_header(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        if self.username and self.password:
            raw = f"{self.username}:{self.password}".encode("utf-8")
            return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
        return {}

    def _request(self, path: str, headers: dict[str, str] | None = None):
        request = urllib.request.Request(self.base_url + path)
        for key, value in self._auth_header().items():
            request.add_header(key, value)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        return urllib.request.urlopen(request, timeout=self.timeout, context=self.context)

    def fetch_token(self, repository: str) -> None:
        """Get a pull token from the registry's /service/token endpoint."""
        query = urllib.parse.urlencode(
            {"service": "harbor-registry", "scope": f"repository:{repository}:pull"}
        )
        path = f"/service/token?{query}"
        request = urllib.request.Request(self.base_url + path)
        if self.username and self.password:
            raw = f"{self.username}:{self.password}".encode("utf-8")
            request.add_header(
                "Authorization", "Basic " + base64.b64encode(raw).decode("ascii")
            )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=self.context
            ) as response:
                payload = json.load(response)
            self.token = payload.get("token") or payload.get("access_token")
            if not self.token:
                raise RegistryError(
                    "registry token response did not contain token/access_token"
                )
        except urllib.error.HTTPError as exc:
            # Some registries allow anonymous pulls without a token endpoint.
            if exc.code in (401, 404):
                self.token = None
                return
            raise RegistryError(f"token endpoint returned HTTP {exc.code}") from exc

    def get_manifest(self, repository: str, reference: str) -> tuple[dict, str]:
        try:
            with self._request(
                f"/v2/{repository}/manifests/{reference}",
                {"Accept": MANIFEST_ACCEPT},
            ) as response:
                content_type = response.headers.get("Content-Type", "")
                payload = json.load(response)
                digest = response.headers.get("Docker-Content-Digest", "")
                return payload, content_type or digest
        except urllib.error.HTTPError as exc:
            raise RegistryError(
                f"manifest {repository}:{reference} returned HTTP {exc.code}"
            ) from exc

    def download_blob(self, repository: str, digest: str, destination: str) -> None:
        try:
            with self._request(f"/v2/{repository}/blobs/{digest}") as response:
                with open(destination, "wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
        except urllib.error.HTTPError as exc:
            raise RegistryError(f"blob {digest} returned HTTP {exc.code}") from exc


def parse_image(image: str) -> tuple[str, str, str]:
    if "@" in image:
        name, digest = image.split("@", 1)
        reference = digest
        tag = None
    else:
        name = image
        last_slash = image.rfind("/")
        last_colon = image.rfind(":")
        if last_colon > last_slash:
            name, tag = image[:last_colon], image[last_colon + 1 :]
            reference = tag
        else:
            tag = None
            reference = "latest"
    if "/" not in name:
        raise RegistryError(
            f"image must include a registry, for example registry/repo:tag (got {image!r})"
        )
    registry, repository = name.split("/", 1)
    if not registry or not repository:
        raise RegistryError(f"could not parse image reference {image!r}")
    return registry, repository, reference


def select_manifest(payload: dict) -> str | None:
    """Return a child digest when payload is an index/manifest list."""
    media_type = payload.get("mediaType", "")
    if "manifest.list" not in media_type and "image.index" not in media_type:
        return None
    manifests = payload.get("manifests") or []
    candidates = []
    for item in manifests:
        platform = item.get("platform") or {}
        if platform.get("os") == "linux" and platform.get("architecture") == "amd64":
            candidates.append(item)
    chosen = candidates[0] if candidates else (manifests[0] if manifests else None)
    if not chosen or not chosen.get("digest"):
        raise RegistryError("manifest index did not contain a usable linux/amd64 image")
    return chosen["digest"]


def extract_from_layers(
    client: RegistryClient, repository: str, layers: list[dict], output: str
) -> bool:
    with tempfile.TemporaryDirectory(prefix="nddsjava-") as scratch:
        for index, layer in enumerate(layers, start=1):
            digest = layer.get("digest")
            if not digest:
                continue
            blob_path = os.path.join(scratch, f"layer-{index}.tar")
            print(f"  downloading layer {index}/{len(layers)} ({digest[:19]}…)")
            client.download_blob(repository, digest, blob_path)
            try:
                with tarfile.open(blob_path, mode="r:*") as archive:
                    for member in archive.getmembers():
                        normalized = member.name.lstrip("./")
                        if normalized == TARGET_MEMBER or normalized.endswith(
                            "/lib/nddsjava.jar"
                        ):
                            extracted = archive.extractfile(member)
                            if extracted is None:
                                continue
                            data = extracted.read()
                            if not data.startswith(b"PK"):
                                raise RegistryError(
                                    f"{normalized} does not look like a JAR"
                                )
                            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
                            with open(output, "wb") as handle:
                                handle.write(data)
                            print(
                                f"extracted {normalized} -> {output} "
                                f"({len(data)} bytes)"
                            )
                            return True
            except tarfile.TarError:
                print(f"  layer {index} is not a tar archive; skipping")
            finally:
                try:
                    os.remove(blob_path)
                except OSError:
                    pass
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="platform runtime image")
    parser.add_argument(
        "--output",
        default="collector/lib/nddsjava.jar",
        help="destination for nddsjava.jar",
    )
    parser.add_argument("--username", default=os.getenv("REGISTRY_USERNAME"))
    parser.add_argument("--password", default=os.getenv("REGISTRY_PASSWORD"))
    parser.add_argument(
        "--verify-tls",
        action="store_true",
        help="verify the registry TLS certificate (lab Harbor uses a self-signed cert)",
    )
    args = parser.parse_args()

    try:
        registry, repository, reference = parse_image(args.image)
        print(f"registry:   {registry}")
        print(f"repository: {repository}")
        print(f"reference:  {reference}")

        client = RegistryClient(
            registry,
            username=args.username,
            password=args.password,
            verify_tls=args.verify_tls,
        )
        client.fetch_token(repository)
        payload, media = client.get_manifest(repository, reference)
        child = select_manifest(payload)
        if child:
            print(f"manifest index -> {child}")
            payload, media = client.get_manifest(repository, child)

        layers = payload.get("layers") or []
        if not layers:
            raise RegistryError("manifest did not contain any layers")
        if not extract_from_layers(client, repository, layers, args.output):
            raise RegistryError(
                f"{TARGET_MEMBER} was not found in any image layer"
            )
        return 0
    except (RegistryError, urllib.error.URLError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
