Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")
sDir = oFSO.GetParentFolderName(WScript.ScriptFullName)
oShell.CurrentDirectory = sDir
oShell.Run "pythonw ""Python Scripts\rivals_gui.py""", 0, False
