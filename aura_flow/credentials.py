from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


class ApiCredentialStore:
    """Stores an optional API key with Windows user-scoped DPAPI encryption."""

    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
        buffer = ctypes.create_string_buffer(value)
        blob = _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        return blob, buffer

    def save(self, value: str) -> None:
        key = value.strip()
        if not key:
            self.clear()
            return
        if os.name != "nt":
            raise RuntimeError("Secure API-key storage is available on Windows only")
        source, source_buffer = self._blob(key.encode("utf-8"))
        protected = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptProtectData(
            ctypes.byref(source),
            "yapper API key",
            None,
            None,
            None,
            0x01,
            ctypes.byref(protected),
        ):
            raise ctypes.WinError()
        del source_buffer
        try:
            payload = ctypes.string_at(protected.pbData, protected.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(protected.pbData)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, self.path)

    def load(self) -> str:
        if os.name != "nt" or not self.path.is_file():
            return ""
        payload = self.path.read_bytes()
        source, source_buffer = self._blob(payload)
        plain = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptUnprotectData(
            ctypes.byref(source),
            None,
            None,
            None,
            None,
            0x01,
            ctypes.byref(plain),
        ):
            return ""
        del source_buffer
        try:
            return ctypes.string_at(plain.pbData, plain.cbData).decode("utf-8")
        except UnicodeDecodeError:
            return ""
        finally:
            ctypes.windll.kernel32.LocalFree(plain.pbData)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
