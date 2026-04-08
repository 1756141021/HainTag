# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(0, 7, 1, 0),
    prodvers=(0, 7, 1, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Hein'),
        StringStruct('FileDescription', 'HainTag - 海茵的标签工坊'),
        StringStruct('FileVersion', '0.7.1.0'),
        StringStruct('InternalName', 'HainTag'),
        StringStruct('OriginalFilename', 'HainTag.exe'),
        StringStruct('ProductName', 'HainTag'),
        StringStruct('ProductVersion', '0.7.1.0'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
