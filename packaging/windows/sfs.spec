# -*- mode: python -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Pacote Windows do SFS (F3): `pyinstaller packaging\windows\sfs.spec` na raiz do repo.
# Saída: dist\SombreroFileSearch\{SombreroFileSearch.exe, sfs.exe, _internal\};
# (NÃO "SFS.exe" + "sfs.exe": no Windows é o MESMO arquivo — o segundo sobrescrevia o primeiro); o build_windows.ps1
# põe bin\ (motores), assets\, LICENSE e VERSION ao lado — onde engine.py e app.py
# procuram (dirname(dirname(__file__)) do módulo = a pasta do pacote).
import os
RAIZ = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
LFS = os.path.join(RAIZ, "lfs")
ICO = os.path.join(RAIZ, "dist", "sfs.ico")

# Qt que o SFS não usa: fora (o pacote cai à metade)
FORA = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
        "PySide6.QtQuick3D", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtTest",
        "PySide6.QtDesigner", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSerialPort",
        "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtRemoteObjects",
        "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtTextToSpeech", "PySide6.QtWebSockets",
        "PySide6.QtHttpServer", "PySide6.QtSpatialAudio", "PySide6.QtGraphs", "tkinter"]

# todos os módulos do lfs entram (são importados por nome "flat" e por pacote)
MODS = [f[:-3] for f in os.listdir(LFS) if f.endswith(".py")]


def analise(script):
    return Analysis([os.path.join(SPECPATH, script)], pathex=[LFS, SPECPATH],
                    hiddenimports=MODS, excludes=FORA, noarchive=False)


NOME_GUI, NOME_CLI = "SombreroFileSearch", "sfs"
assert NOME_GUI.lower() != NOME_CLI.lower(), "NTFS: nomes iguais sem caixa = um exe sobrescreve o outro"
a_gui, a_cli = analise("sfs_gui.py"), analise("sfs_cli.py")
MERGE((a_gui, "sfs_gui", NOME_GUI), (a_cli, "sfs_cli", NOME_CLI))

exe_gui = EXE(PYZ(a_gui.pure), a_gui.scripts, [], exclude_binaries=True, name=NOME_GUI,
              console=False, icon=ICO if os.path.exists(ICO) else None)
exe_cli = EXE(PYZ(a_cli.pure), a_cli.scripts, [], exclude_binaries=True, name=NOME_CLI,
              console=True, icon=ICO if os.path.exists(ICO) else None)
COLLECT(exe_gui, a_gui.binaries, a_gui.datas, exe_cli, a_cli.binaries, a_cli.datas,
        name="SombreroFileSearch")
