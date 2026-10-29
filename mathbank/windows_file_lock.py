"""Nonblocking Windows shared/exclusive byte locks for document-project leases.

CRT LK_NBRLCK is exclusive despite its name. Use LockFileEx on the caller's
existing descriptor; descriptor ownership remains with the caller.
"""
from __future__ import annotations

import ctypes
import errno
from functools import lru_cache
import os


class _Overlapped(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", ctypes.c_uint32),
        ("OffsetHigh", ctypes.c_uint32),
        ("hEvent", ctypes.c_void_p),
    ]


@lru_cache(maxsize=1)
def _get_api():
    if os.name != "nt":
        raise OSError("Windows file locks are unavailable on this platform")
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LockFileEx.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_uint32, ctypes.POINTER(_Overlapped),
    ]
    kernel32.LockFileEx.restype = ctypes.c_int
    kernel32.UnlockFileEx.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.POINTER(_Overlapped),
    ]
    kernel32.UnlockFileEx.restype = ctypes.c_int
    return kernel32, msvcrt.get_osfhandle, ctypes.get_last_error


def _failure(code, *, acquiring):
    if acquiring and code == 33:  # ERROR_LOCK_VIOLATION
        error = BlockingIOError(errno.EAGAIN, "Windows file lock is busy")
    else:
        error = OSError(code, "Windows file lock operation failed")
    error.winerror = code
    return error


def lock(fd, *, shared):
    api, get_handle, last_error = _get_api()
    overlapped = _Overlapped()
    # FAIL_IMMEDIATELY; without EXCLUSIVE, LockFileEx grants a shared lock.
    flags = 1 | (0 if shared else 2)
    if not api.LockFileEx(get_handle(fd), flags, 0, 1, 0, ctypes.byref(overlapped)):
        raise _failure(last_error(), acquiring=True)


def unlock(fd):
    api, get_handle, last_error = _get_api()
    overlapped = _Overlapped()
    if not api.UnlockFileEx(get_handle(fd), 0, 1, 0, ctypes.byref(overlapped)):
        raise _failure(last_error(), acquiring=False)
