#!/usr/bin/env python3
"""
Compare Terraform AWS Provider documentation for a list of AWS resources
between two versions and output the differences in a JSON file.
The script fetches the official markdown documentation for each resource from
the hashicorp/terraform-provider-aws GitHub repository, compares the
documentation between two given versions using SHA-256 hashes, and writes
only the changed resources (or resources whose documentation could not be
fetched) to an output JSON file.

Example usage:
    python compare_aws_provider_versions.py \
        --current-version 5.100.0 \
        --latest-version 6.45.0 \
        --resources aws_s3_bucket,aws_iam_role,aws_rds_cluster \
        --output ./provider-doc-changes.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

GITHUB_BASE_URL = "https://raw.githubusercontent.com/hashicorp/terraform-provider-aws"
DOCS_PATH_TEMPLATE = "website/docs/r/{resource}.html.markdown"
HTTP_TIMEOUT_SECONDS = 30  # seconds


def parse_args() -> argparse.Namespace:
    """Parse and return command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compare AWS provider documentation between versions."
    )
    parser.add_argument(
        "--current-version", required=True, help="Current version of the AWS provider."
    )
    parser.add_argument(
        "--latest-version", required=True, help="Latest version of the AWS provider."
    )
    parser.add_argument(
        "--resources",
        required=True,
        help="Comma-separated list of AWS resources to compare.",
    )
    parser.add_argument("--output", required=True, help="Output JSON file path.")

    return parser.parse_args()


def normalize_version_tag(version: str) -> str:
    """Ensure the version is prefixed with 'v' for GitHub tags."""
    version = version.strip()
    if not version:
        raise ValueError("Version must be a non-empty string.")
    if version.startswith("v"):
        return version
    return f"v{version}"


def parse_resources(raw: str) -> list[str]:
    """Parse a comma-separated string of resources into a list."""
    resources = [r.strip() for r in raw.split(",") if r.strip()]
    if not resources:
        raise ValueError(
            "No valid resources provided. Please provide a comma-separated list of resources in --resources argument."
        )
    return resources


def resource_to_doc_path(resource: str) -> str:
    """Convert an AWS resource name to its documentation file path.

    The 'aws_' prefix is stripped if present.

    Examples:
        aws_s3_bucket         -> website/docs/r/s3_bucket.html.markdown
        aws_codebuild_project -> website/docs/r/codebuild_project.html.markdown
        s3_bucket             -> website/docs/r/s3_bucket.html.markdown
    """
    name = resource.strip()
    if name.startswith("aws_"):
        name = name[len("aws_") :]
    return DOCS_PATH_TEMPLATE.format(resource=name)


def build_doc_url(version_tag: str, doc_path: str) -> str:
    """Construct the URL to the documentation file using a version tag and document path."""
    return f"{GITHUB_BASE_URL}/{version_tag}/{doc_path}"


def fetch_documentation(url: str) -> Optional[bytes]:
    """Fetch the raw documentation content from a URL.

    Returns the raw response body as bytes if the file exists, or None if the
    file could not be fetched (e.g. 404, network error). Hashing is done on
    the raw bytes to avoid any normalization.
    """
    req = urllib_request.Request(
        url,
        headers={"User-Agent": "compare-aws-provider-versions/1.0"},
    )
    try:
        with urllib_request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                return None
            return resp.read()
    except urllib_error.HTTPError:
        # 404 and similar - documentation file does not exist for this version.
        return None
    except urllib_error.URLError:
        # Network-level error - treat as unfetchable.
        return None
    except TimeoutError:
        return None


def sha256_hex(content: bytes) -> str:
    """Return the SHA-256 hex digest of the given bytes."""
    return hashlib.sha256(content).hexdigest()


def compare_resource(
    resource: str,
    current_version: str,
    latest_version: str,
    current_tag: str,
    latest_tag: str,
) -> Optional[dict]:
    """Compare documentation for a single resource between two versions.

    Returns:
        - A dict describing the change if documentation differs.
        - A dict with an 'error' field if one or both files could not be fetched.
        - None if the documentation is identical between the two versions.
    """
    doc_path = resource_to_doc_path(resource)
    current_url = build_doc_url(current_tag, doc_path)
    latest_url = build_doc_url(latest_tag, doc_path)

    current_content = fetch_documentation(current_url)
    latest_content = fetch_documentation(latest_url)

    if current_content is None or latest_content is None:
        return {
            "resource": resource,
            "current_provider_version": current_version,
            "latest_provider_version": latest_version,
            "current_provider_tag": current_tag,
            "latest_provider_tag": latest_tag,
            "documentation_file": doc_path,
            "current_documentation_url": current_url,
            "latest_documentation_url": latest_url,
            "error": (
                "Documentation file could not be fetched for one or both "
                "provider versions"
            ),
        }

    current_hash = sha256_hex(current_content)
    latest_hash = sha256_hex(latest_content)

    if current_hash == latest_hash:
        return None

    return {
        "resource": resource,
        "current_provider_version": current_version,
        "latest_provider_version": latest_version,
        "current_provider_tag": current_tag,
        "latest_provider_tag": latest_tag,
        "documentation_file": doc_path,
        "current_documentation_url": current_url,
        "latest_documentation_url": latest_url,
        "current_documentation_hash": current_hash,
        "latest_documentation_hash": latest_hash,
    }


def write_output(path: str, results: list[dict]) -> None:
    """Write the results list as JSON to the given path."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        f.write("\n")


def main() -> int:
    args = parse_args()

    try:
        resources = parse_resources(args.resources)
        current_tag = normalize_version_tag(args.current_version)
        latest_tag = normalize_version_tag(args.latest_version)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    results: list[dict] = []
    for resource in resources:
        entry = compare_resource(
            resource=resource,
            current_version=args.current_version,
            latest_version=args.latest_version,
            current_tag=current_tag,
            latest_tag=latest_tag,
        )
        if entry is not None:
            results.append(entry)

    write_output(args.output, results)
    print(
        f"Wrote {len(results)} changed/errored resource(s) to {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
