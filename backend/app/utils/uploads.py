from fastapi import UploadFile

BYTES_PER_MB = 1024 * 1024


class UploadTooLargeError(Exception):
    def __init__(self, max_size_mb: int):
        self.max_size_mb = max_size_mb
        super().__init__(f"File exceeds the {max_size_mb} MB upload limit")


async def read_upload_within_limit(upload: UploadFile, max_size_mb: int) -> bytes:
    max_bytes = max_size_mb * BYTES_PER_MB
    if upload.size is not None and upload.size > max_bytes:
        raise UploadTooLargeError(max_size_mb)
    # Reading one byte past the limit catches a body whose size is unknown or understated
    # without ever holding more than limit + 1 bytes in memory.
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise UploadTooLargeError(max_size_mb)
    return content
