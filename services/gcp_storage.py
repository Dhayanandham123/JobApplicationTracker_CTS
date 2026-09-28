"""Google Cloud Storage helper. Disabled (returns None/False) when GCS_BUCKET is unset,
so local development keeps working with the local instance/ folder."""
import os
import logging

logger = logging.getLogger(__name__)
_client = None


def enabled():
    return bool(os.environ.get('GCS_BUCKET'))


def _bucket():
    global _client
    from google.cloud import storage
    if _client is None:
        _client = storage.Client()  # uses Cloud Run service account automatically
    return _client.bucket(os.environ['GCS_BUCKET'])


def upload_bytes(blob_name, data, content_type='application/octet-stream'):
    if not enabled():
        return False
    try:
        _bucket().blob(blob_name).upload_from_string(data, content_type=content_type)
        return True
    except Exception as e:
        logger.error(f"GCS upload failed for {blob_name}: {e}")
        return False


def download_bytes(blob_name):
    if not enabled():
        return None
    try:
        blob = _bucket().blob(blob_name)
        return blob.download_as_bytes() if blob.exists() else None
    except Exception as e:
        logger.error(f"GCS download failed for {blob_name}: {e}")
        return None


def delete(blob_name):
    if not enabled():
        return False
    try:
        blob = _bucket().blob(blob_name)
        if blob.exists():
            blob.delete()
        return True
    except Exception as e:
        logger.error(f"GCS delete failed for {blob_name}: {e}")
        return False
