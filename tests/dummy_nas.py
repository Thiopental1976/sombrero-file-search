#!/usr/bin/env python3
"""NAS falso: FUSE passthrough com latência injetável e travamento controlável.
Controle por arquivos em /tmp/nas_ctl/: 'latency_ms' (int) e 'hang' (existe = trava tudo)."""
import os, sys, time, errno
from fuse import FUSE, Operations, FuseOSError
CTL="/tmp/nas_ctl"
def _lat():
    try: return int(open(CTL+"/latency_ms").read().strip())/1000.0
    except Exception: return 0.0
def _gate():
    while os.path.exists(CTL+"/hang"): time.sleep(0.2)   # trava dura enquanto o flag existir
    t=_lat()
    if t: time.sleep(t)
class PassNAS(Operations):
    def __init__(s, root): s.root=os.path.realpath(root)
    def _p(s, path): return os.path.join(s.root, path.lstrip("/"))
    def getattr(s, path, fh=None):
        _gate()
        try: st=os.lstat(s._p(path))
        except OSError as e: raise FuseOSError(e.errno)
        return {k:getattr(st,k) for k in ("st_mode","st_size","st_mtime","st_atime","st_ctime","st_nlink","st_uid","st_gid")}
    def readdir(s, path, fh):
        _gate(); return [".",".."]+os.listdir(s._p(path))
    def open(s, path, flags):
        _gate(); return os.open(s._p(path), flags)
    def read(s, path, size, off, fh):
        _gate(); os.lseek(fh, off, 0); return os.read(fh, size)
    def release(s, path, fh): os.close(fh); return 0
    def create(s, path, mode, fi=None):
        _gate(); return os.open(s._p(path), os.O_WRONLY|os.O_CREAT|os.O_TRUNC, mode)
    def write(s, path, data, off, fh):
        _gate(); os.lseek(fh, off, 0); return os.write(fh, data)
    def truncate(s, path, length, fh=None):
        _gate()
        fd=os.open(s._p(path), os.O_RDWR|os.O_CREAT, 0o644)
        try: os.ftruncate(fd, length)
        finally: os.close(fd)
    def unlink(s, path): _gate(); os.unlink(s._p(path))
    def mkdir(s, path, mode): _gate(); os.mkdir(s._p(path), mode)
    def rename(s, old, new): _gate(); os.rename(s._p(old), s._p(new))
    def statfs(s, path):
        st=os.statvfs(s.root)
        return {k:getattr(st,k) for k in ("f_bavail","f_bfree","f_blocks","f_bsize","f_frsize","f_namemax","f_files","f_ffree")}
if __name__=="__main__":
    backing, mnt = sys.argv[1], sys.argv[2]
    os.makedirs(CTL, exist_ok=True)
    FUSE(PassNAS(backing), mnt, foreground=True, fsname="dummynas", subtype="sshfs", allow_other=False)

