"""Windows native folder picker; invoked only by the user's Choose button."""
import ctypes
from ctypes import wintypes

def choose_folder(initial=''):
    ole=ctypes.OleDLL('ole32');shell=ctypes.WinDLL('shell32');user=ctypes.WinDLL('user32')
    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD]
    ole.CoInitializeEx.restype=ctypes.c_long
    initialized=ole.CoInitializeEx(None,2) in (0,1)
    CALLBACK=ctypes.WINFUNCTYPE(ctypes.c_int,wintypes.HWND,ctypes.c_uint,ctypes.c_ssize_t,ctypes.c_ssize_t)
    user.SendMessageW.argtypes=[wintypes.HWND,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
    user.SendMessageW.restype=ctypes.c_ssize_t
    user.SetForegroundWindow.argtypes=[wintypes.HWND]
    initial_buffer=ctypes.create_unicode_buffer(str(initial))
    @CALLBACK
    def callback(hwnd,message,lparam,data):
        if message==1:
            if initial:user.SendMessageW(hwnd,0x467,1,ctypes.addressof(initial_buffer))
            user.SetForegroundWindow(hwnd)
        return 0
    class BROWSEINFO(ctypes.Structure):
        _fields_=[('hwndOwner',wintypes.HWND),('pidlRoot',ctypes.c_void_p),
                  ('pszDisplayName',wintypes.LPWSTR),('lpszTitle',wintypes.LPCWSTR),
                  ('ulFlags',wintypes.UINT),('lpfn',CALLBACK),('lParam',ctypes.c_ssize_t),('iImage',ctypes.c_int)]
    display=ctypes.create_unicode_buffer(32768)
    info=BROWSEINFO(None,None,ctypes.cast(display,wintypes.LPWSTR),'��ܭ׹Ͽ�X��Ƨ�',0x1|0x40,callback,0,0)
    shell.SHBrowseForFolderW.argtypes=[ctypes.POINTER(BROWSEINFO)]
    shell.SHBrowseForFolderW.restype=ctypes.c_void_p
    shell.SHGetPathFromIDListEx.argtypes=[ctypes.c_void_p,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
    shell.SHGetPathFromIDListEx.restype=wintypes.BOOL
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
    pidl=None
    try:
        pidl=shell.SHBrowseForFolderW(ctypes.byref(info))
        if not pidl:return None
        result=ctypes.create_unicode_buffer(32768)
        if not shell.SHGetPathFromIDListEx(pidl,result,len(result),0):
            raise ValueError('�п�ܹ�ڪ��ɮ׸�Ƨ�')
        return result.value
    finally:
        if pidl:ole.CoTaskMemFree(pidl)
        if initialized:ole.CoUninitialize()
