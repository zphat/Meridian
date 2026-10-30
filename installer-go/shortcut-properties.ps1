Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class MeridianShortcutProperties {
    [StructLayout(LayoutKind.Sequential)]
    public struct PropertyKey { public Guid format; public uint id; }
    [StructLayout(LayoutKind.Explicit, Size=24)]
    public struct PropVariant {
        [FieldOffset(0)] public ushort type;
        [FieldOffset(8)] public IntPtr value;
    }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        uint GetCount();
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }
    [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=false)]
    static extern void SHGetPropertyStoreFromParsingName(string path, IntPtr context, uint flags,
        ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);
    [DllImport("shell32.dll")]
    static extern void SHChangeNotify(uint eventId, uint flags, IntPtr item1, IntPtr item2);
    public static void SetAppId(string path, string appId) {
        var iid=typeof(IPropertyStore).GUID;
        IPropertyStore store;
        SHGetPropertyStoreFromParsingName(path,IntPtr.Zero,2,ref iid,out store);
        var key=new PropertyKey { format=new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), id=5 };
        var value=new PropVariant { type=31, value=Marshal.StringToCoTaskMemUni(appId) };
        try { store.SetValue(ref key,ref value);store.Commit(); }
        finally { Marshal.FreeCoTaskMem(value.value);Marshal.ReleaseComObject(store); }
        var name=Marshal.StringToCoTaskMemUni(path);
        try { SHChangeNotify(0x2000,5,name,IntPtr.Zero); }
        finally { Marshal.FreeCoTaskMem(name); }
    }
    public static void Refresh() { SHChangeNotify(0x08000000,0,IntPtr.Zero,IntPtr.Zero); }
}
'@
