"""Publish server-side saved data under the same lock as CMS editing.

No credentials or editable datasets are changed. Public output is backed up on
the server before replacement; previously public media is never removed.
"""
import hashlib
import json
import tarfile
import time
from server import ROOT, PUBLIC, LOCK, update_site


def protected_hashes():
    paths = list((ROOT / 'assets').glob('*.json'))
    for folder in ('admin/private', 'assets/people', 'assets/files', 'assets/originals/uploads'):
        paths.extend(p for p in (ROOT / folder).rglob('*') if p.is_file() and p.name != 'edit.lock')
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def publish():
    if not PUBLIC: raise RuntimeError('正式站目录未配置')
    with LOCK:
        before = protected_hashes()
        backup = ROOT / 'admin/backups/published' / ('maintenance-' + time.strftime('%Y%m%d-%H%M%S') + '.tar.gz')
        backup.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(backup, 'w:gz') as archive:
            for name in ('index.html', 'data'):
                if (PUBLIC / name).exists(): archive.add(PUBLIC / name, arcname=name)
        backup.chmod(0o600)
        try:
            update_site()
            if before != protected_hashes(): raise RuntimeError('受保护资料发生变化，请停止核查')
        except Exception:
            # This archive contains only our previously public index/data.
            with tarfile.open(backup) as archive: archive.extractall(PUBLIC)
            raise
        print(json.dumps({'protected_files': len(before), 'protected_unchanged': True,
                          'public_backup': str(backup), 'homepage_sha256': hashlib.sha256((PUBLIC / 'index.html').read_bytes()).hexdigest()}))


if __name__ == '__main__': publish()
