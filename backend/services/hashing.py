"""
Evidence integrity hashing.
SHA-256 is treated as the primary evidence hash; MD5/SHA-1 kept for
compatibility with older case-management tooling.
"""
import hashlib


def hash_file(path, chunk_size=65536):
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
            md5.update(chunk)
            sha1.update(chunk)
    return {
        "sha256": sha256.hexdigest(),
        "md5": md5.hexdigest(),
        "sha1": sha1.hexdigest(),
    }
