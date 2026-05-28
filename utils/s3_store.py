"""
S3 storage backend for htDash.

Mirrors the local `data/` folder structure as S3 keys under the `homerclouds` bucket.
All keys are relative paths (no leading slash), e.g.:
    ranipet/patients/HOCMCV002/HOCMCV002.json
    ranipet/devices/inventory/pluto.json

Only used when Config.USE_S3 is True. The local file backend in data_access.py
remains the default (USE_S3=false).
"""

import io
import json
import tempfile
import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from config import Config

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client('s3')
    return _s3


# ── JSON objects ──────────────────────────────────────────────────────────────

def s3_read_json(key: str) -> Optional[dict]:
    """Fetch and parse a JSON object from S3. Returns None if not found."""
    try:
        resp = _client().get_object(Bucket=Config.BUCKET_NAME, Key=key)
        return json.loads(resp['Body'].read().decode('utf-8'))
    except ClientError as e:
        if e.response['Error']['Code'] in ('NoSuchKey', '404'):
            return None
        raise
    except Exception:
        return None


def s3_write_json(key: str, data: dict) -> None:
    """Serialize and upload a JSON object to S3."""
    body = json.dumps(data, indent=2).encode('utf-8')
    _client().put_object(
        Bucket=Config.BUCKET_NAME,
        Key=key,
        Body=body,
        ContentType='application/json',
    )


# ── Text / CSV / log files ────────────────────────────────────────────────────

def s3_read_text(key: str) -> Optional[str]:
    """Fetch a text object from S3. Returns None if not found."""
    try:
        resp = _client().get_object(Bucket=Config.BUCKET_NAME, Key=key)
        return resp['Body'].read().decode('utf-8')
    except ClientError as e:
        if e.response['Error']['Code'] in ('NoSuchKey', '404'):
            return None
        raise
    except Exception:
        return None


def s3_write_text(key: str, content: str) -> None:
    """Upload a text string to S3."""
    _client().put_object(
        Bucket=Config.BUCKET_NAME,
        Key=key,
        Body=content.encode('utf-8'),
        ContentType='text/plain',
    )


def s3_append_text(key: str, line: str) -> None:
    """Append a line to a text object in S3 (read-modify-write).
    Creates the object if it doesn't exist yet.
    """
    existing = s3_read_text(key) or ''
    s3_write_text(key, existing + line)


# ── Key listing ───────────────────────────────────────────────────────────────

def s3_list_prefix(prefix: str) -> list:
    """Return all object keys under a prefix (non-recursive, just immediate children)."""
    paginator = _client().get_paginator('list_objects_v2')
    keys = []
    for page in paginator.paginate(Bucket=Config.BUCKET_NAME, Prefix=prefix):
        for obj in page.get('Contents', []):
            keys.append(obj['Key'])
    return keys


def s3_list_immediate_folders(prefix: str) -> list:
    """Return the names of immediate 'subdirectories' under prefix using delimiter."""
    if not prefix.endswith('/'):
        prefix += '/'
    resp = _client().list_objects_v2(
        Bucket=Config.BUCKET_NAME,
        Prefix=prefix,
        Delimiter='/',
    )
    folders = []
    for cp in resp.get('CommonPrefixes', []):
        # cp['Prefix'] = "ranipet/patients/HOCMCV002/"
        name = cp['Prefix'].rstrip('/').split('/')[-1]
        if name:
            folders.append(name)
    return folders


def s3_key_exists(key: str) -> bool:
    """Return True if the key exists in the bucket."""
    try:
        _client().head_object(Bucket=Config.BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] in ('404', 'NoSuchKey'):
            return False
        raise


# ── Binary file upload / download ─────────────────────────────────────────────

def s3_upload_file(local_path: str, key: str, content_type: str = 'application/octet-stream') -> None:
    """Upload a local file to S3."""
    _client().upload_file(local_path, Config.BUCKET_NAME, key,
                          ExtraArgs={'ContentType': content_type})


def s3_download_file(key: str, local_path: str) -> None:
    """Download an S3 object to a local path."""
    _client().download_file(Config.BUCKET_NAME, key, local_path)


def s3_get_bytes(key: str) -> Optional[bytes]:
    """Return raw bytes of an S3 object, or None if not found."""
    try:
        resp = _client().get_object(Bucket=Config.BUCKET_NAME, Key=key)
        return resp['Body'].read()
    except ClientError as e:
        if e.response['Error']['Code'] in ('NoSuchKey', '404'):
            return None
        raise


def s3_upload_bytes(key: str, data: bytes, content_type: str = 'application/octet-stream') -> None:
    """Upload raw bytes to S3 under the given key."""
    _client().put_object(
        Bucket=Config.BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
