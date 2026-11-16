"""Publish server-side saved data under the same lock as CMS editing.

Credentials and media are unchanged. Missing legacy article tags are migrated
once; explicit tags, including an empty selection, are always preserved.
Source news and public output are backed up before replacement.
"""
import hashlib
import json
import tarfile
import time
import os
import tempfile
from schema import validate
from server import ROOT, PUBLIC, LOCK, update_site


def protected_hashes():
    paths = list((ROOT / 'assets').glob('*.json'))
    for folder in ('admin/private', 'assets/people', 'assets/files', 'assets/originals/uploads'):
        paths.extend(p for p in (ROOT / folder).rglob('*') if p.is_file() and p.name != 'edit.lock')
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def migrate_legacy_series(rows):
    """Move only absent legacy tags to editable article data; preserve clearing."""
    legacy = {1084: "tour", 1082: "national", 1087: "policy",
              1088: "policy", 1085: "mentor", 1086: "mentor"}
    changed = []
    for row in rows:
        if row.get("id") in legacy and "tag" not in row:
            row["tag"] = legacy[row["id"]]
            changed.append(row["id"])
    return changed


def replace_news(path, raw):
    mode = path.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
        file.write(raw)
        temporary = file.name
    try:
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish():
    if not PUBLIC: raise RuntimeError('正式站目录未配置')
    with LOCK:
        before = protected_hashes()
        backup = ROOT / 'admin/backups/published' / ('maintenance-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(time.time_ns()) + '.tar.gz')
        backup.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(backup, 'w:gz') as archive:
            for name in ('index.html', 'data'):
                if (PUBLIC / name).exists(): archive.add(PUBLIC / name, arcname=name)
        backup.chmod(0o600)
        news_path = ROOT / 'assets/news.json'
        news_before = news_path.read_bytes()
        news_backup = backup.with_suffix('.news.json')
        rows = json.loads(news_before)
        migrated = migrate_legacy_series(rows)
        if migrated:
            validate('news', rows)
            news_backup.write_bytes(news_before)
            news_backup.chmod(0o600)
        try:
            if migrated:
                replace_news(news_path, (json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode())
                before['assets/news.json'] = hashlib.sha256(news_path.read_bytes()).hexdigest()
            update_site()
            if before != protected_hashes(): raise RuntimeError('受保护资料发生变化，请停止核查')
        except Exception:
            if migrated:
                replace_news(news_path, news_before)
            # This archive contains only our previously public index/data.
            with tarfile.open(backup) as archive: archive.extractall(PUBLIC)
            raise
        print(json.dumps({'protected_files': len(before), 'protected_unchanged': True,
                          'public_backup': str(backup), 'migrated_article_ids': migrated,
                          'source_news_backup': str(news_backup) if migrated else None, 'homepage_sha256': hashlib.sha256((PUBLIC / 'index.html').read_bytes()).hexdigest()}))


if __name__ == '__main__': publish()
