"""Native video-only device identities in OpenCV's backend enumeration order.

No audio enumeration or extra dependency. Each call belongs to a disposable
capture child, so COM / Media Foundation state never survives a failed session.
"""
import ctypes as C
from contextlib import contextmanager
from uuid import UUID


def guid(value):
    return (C.c_ubyte * 16).from_buffer_copy(UUID(value).bytes_le)


def call(obj, slot, types, *args):
    table = C.cast(obj, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(C.c_long, C.c_void_p, *types)(table[slot])(obj, *args)


def checked(hr):
    if hr < 0:
        raise OSError(f'Windows camera enumeration HRESULT 0x{hr & 0xffffffff:08x}')


@contextmanager
def owned(obj):
    try:
        yield obj
    finally:
        if obj:
            call(obj, 2, [])


def media_foundation():
    mf = C.WinDLL('mf.dll'); platform = C.WinDLL('mfplat.dll'); ole = C.OleDLL('ole32')
    checked(platform.MFStartup(0x20070, 0))
    attrs = C.c_void_p(); array = C.POINTER(C.c_void_p)(); count = C.c_uint()
    try:
        checked(platform.MFCreateAttributes(C.byref(attrs), 1))
        with owned(attrs):
            checked(call(attrs, 24, [C.c_void_p, C.c_void_p],
                         guid('c60ac5fe-252a-478f-a0ef-bc8fa5f7cad3'),
                         guid('8ac3587a-4ae7-42d8-99e0-0a6013eef90f')))
            checked(mf.MFEnumDeviceSources(attrs, C.byref(array), C.byref(count)))
        rows = []
        for i in range(count.value):
            with owned(array[i]) as device:
                row = {'backend': 'MSMF', 'index': i}
                for key, value in [('name', '60d0e559-52f8-4fa2-bbce-acdb34a8ec01'),
                                   ('device_id', '58f0aad8-22bf-4f8a-bb3d-d2c4978c6e2f')]:
                    string = C.c_void_p(); length = C.c_uint()
                    checked(call(device, 13, [C.c_void_p, C.c_void_p, C.c_void_p],
                                 guid(value), C.byref(string), C.byref(length)))
                    try:
                        row[key] = C.wstring_at(string)
                    finally:
                        ole.CoTaskMemFree(string)
                rows.append(row)
        return rows
    finally:
        if array:
            ole.CoTaskMemFree(array)
        platform.MFShutdown()


def directshow():
    ole = C.OleDLL('ole32'); automation = C.OleDLL('oleaut32')
    dev = C.c_void_p(); enum = C.c_void_p()
    checked(ole.CoCreateInstance(guid('62be5d10-60eb-11d0-bd3b-00a0c911ce86'), None, 1,
                                guid('29840822-5b84-11d0-bd3b-00a0c911ce86'), C.byref(dev)))
    rows = []
    with owned(dev):
        hr = call(dev, 3, [C.c_void_p, C.c_void_p, C.c_uint],
                  guid('860bb310-5d01-11d0-bd3b-00a0c911ce86'), C.byref(enum), 0)
        checked(hr)
        if hr == 1:
            return rows
        with owned(enum):
            while True:
                moniker = C.c_void_p()
                hr = call(enum, 3, [C.c_uint, C.c_void_p, C.c_void_p], 1, C.byref(moniker), None)
                checked(hr)
                if hr == 1:
                    break
                with owned(moniker):
                    bag = C.c_void_p()
                    checked(call(moniker, 9, [C.c_void_p] * 4, None, None,
                                 guid('55272a00-42cb-11ce-8135-00aa004bb851'), C.byref(bag)))
                    with owned(bag):
                        row = {'backend': 'DSHOW', 'index': len(rows)}
                        for key, name in [('name', 'FriendlyName'), ('device_id', 'DevicePath')]:
                            # VARIANT is 24 bytes on Win64; BSTR payload starts at byte 8.
                            variant = C.create_string_buffer(24)
                            hr = call(bag, 3, [C.c_wchar_p, C.c_void_p, C.c_void_p], name, variant, None)
                            try:
                                row[key] = (C.wstring_at(C.c_void_p.from_buffer(variant, 8).value)
                                            if hr >= 0 and C.c_ushort.from_buffer(variant).value == 8 else '')
                            finally:
                                automation.VariantClear(variant)
                        rows.append(row)
    return rows


def enumerate_devices(backend):
    ole = C.OleDLL('ole32')
    checked(ole.CoInitializeEx(None, 0))
    try:
        return media_foundation() if backend == 'MSMF' else directshow()
    finally:
        ole.CoUninitialize()
