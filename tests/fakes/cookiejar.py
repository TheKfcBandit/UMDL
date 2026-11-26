"""Writes a cookie store in Apple's binarycookies format, for the tests.

The helper reads this format to tell which sites are signed in. Only what the
helper reads is filled in: domain, name, path, value and expiry.
"""
import os
import struct

MAC_EPOCH = 978307200  # 1 January 2001, in Unix time


def build(cookies):
    """cookies: iterable of (domain, name) or (domain, name, expires_unix)."""
    records = []
    for cookie in cookies:
        domain, name = cookie[0], cookie[1]
        expires = cookie[2] if len(cookie) > 2 else 4102444800  # 2100
        strings = [text.encode("utf-8") + b"\x00" for text in (domain, name, "/", "value")]
        offsets, position = [], 56
        for text in strings:
            offsets.append(position)
            position += len(text)
        records.append(struct.pack("<iiii", position, 0, 0, 0) + struct.pack("<iiii", *offsets)
                       + b"\x00" * 8
                       + struct.pack("<dd", expires - MAC_EPOCH if expires else 0, 0)
                       + b"".join(strings))
    starts, position = [], 12 + 4 * len(records)
    for record in records:
        starts.append(position)
        position += len(record)
    page = (b"\x00\x00\x01\x00" + struct.pack("<i", len(records))
            + struct.pack("<%di" % len(records), *starts) + b"\x00" * 4 + b"".join(records))
    return b"cook" + struct.pack(">i", 1) + struct.pack(">i", len(page)) + page + b"\x00" * 8


def write(path, cookies):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(build(cookies))
