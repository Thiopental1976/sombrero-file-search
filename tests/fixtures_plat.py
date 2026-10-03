"""Ajudas de teste que valem nos dois SOs (F1 do SFS para Windows, 02/10/2026).

  ENV_CONFIG / ENV_CACHE   variável que plat.config_base()/cache_base() leem
                           (XDG_* no Linux, APPDATA/LOCALAPPDATA no Windows)
  deny_read / allow_read   tira/devolve a leitura de um caminho: chmod 000 no
                           Linux, icacls /deny no Windows (sem administrador)
  pode_negar_leitura()     False quando negar não tem efeito (root no Linux)
  so_linux(motivo)         True no Linux; no Windows imprime "~skip <motivo>" —
                           lacuna CONHECIDA, dita, nunca escondida
  NOMES_BYTES              nomes com byte não-UTF-8 existem? (só no Linux:
                           NTFS guarda UTF-16, não há byte quebrado)
"""
import os, subprocess

WIN = os.name == "nt"
ENV_CONFIG = "APPDATA" if WIN else "XDG_CONFIG_HOME"
ENV_CACHE = "LOCALAPPDATA" if WIN else "XDG_CACHE_HOME"
NOMES_BYTES = not WIN


_PODE_NEGAR = None


def pode_negar_leitura() -> bool:
    """Negar leitura TEM efeito aqui? Linux: não-root. Windows: MEDIDO — um
    administrador com privilégio de backup (sessão SSH elevada, runner do CI)
    lista pasta negada, como o root ignora chmod 000."""
    global _PODE_NEGAR
    if not WIN:
        return os.geteuid() != 0      # root lê tudo: chmod 000 não nega nada
    if _PODE_NEGAR is None:
        import shutil, tempfile
        d = tempfile.mkdtemp(prefix="sfs_sonda_acl_")
        try:
            deny_read(d)
            try:
                os.listdir(d)
                _PODE_NEGAR = False
            except PermissionError:
                _PODE_NEGAR = True
        except Exception:
            _PODE_NEGAR = False
        finally:
            try:
                allow_read(d)
            except Exception:
                pass
            shutil.rmtree(d, ignore_errors=True)
    return _PODE_NEGAR


def _icacls(*args, check=True):
    subprocess.run(["icacls", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=check)


def deny_read(path: str):
    """Tira a leitura (e a listagem, se pasta) do usuário atual."""
    if WIN:
        # só RD (ler dados / listar pasta): negar "R" inteiro tira também o
        # READ_CONTROL, e aí nem o icacls consegue desfazer (medido, exit 5)
        _icacls(path, "/deny", "%s:(RD)" % os.environ.get("USERNAME", "*S-1-1-0"))
    else:
        os.chmod(path, 0)


def allow_read(path: str, modo: int = 0o755):
    """Desfaz deny_read (para o tempdir poder ser apagado)."""
    if WIN:
        if os.path.lexists(path):     # limpeza: caminho já apagado não é erro
            _icacls(path, "/remove:d", os.environ.get("USERNAME", "*S-1-1-0"), check=False)
    elif os.path.lexists(path):
        os.chmod(path, modo)


def so_linux(motivo: str) -> bool:
    if WIN:
        print("~skip  [só Linux] " + motivo)
        return False
    return True


_PODE_LINK = None


def pode_symlink() -> bool:
    """Criar symlink funciona aqui? No Windows, usuário comum sem o "modo
    desenvolvedor" leva WinError 1314 — limitação do SO, não do programa."""
    global _PODE_LINK
    if _PODE_LINK is None:
        import shutil, tempfile
        d = tempfile.mkdtemp(prefix="sfs_sonda_link_")
        try:
            os.symlink(d, os.path.join(d, "l"), target_is_directory=True)
            _PODE_LINK = True
        except (OSError, NotImplementedError):
            _PODE_LINK = False
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return _PODE_LINK
