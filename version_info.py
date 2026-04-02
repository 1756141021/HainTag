# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(0, 3, 0, 0),
    prodvers=(0, 3, 0, 0),
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
        StringStruct('CompanyName', ''),
        StringStruct('FileDescription', 'AI Tag Generator'),
        StringStruct('FileVersion', '0.3.0.0'),
        StringStruct('InternalName', 'AITagGenerator'),
        StringStruct('OriginalFilename', 'AITagGenerator.exe'),
        StringStruct('ProductName', 'AI Tag Generator'),
        StringStruct('ProductVersion', '0.3.0.0'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
