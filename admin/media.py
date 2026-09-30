"""Separate authenticated upload drafts from saved, publishable media."""
import json
from pathlib import Path
import shutil


def draft_root(root):
    return root / 'admin' / 'private' / 'media-drafts'


def draft_manifest_path(root):
    return draft_root(root) / 'manifest.json'


def drafts(root):
    path = draft_manifest_path(root)
    return json.loads(path.read_text()) if path.exists() else {}


def available_manifest(root):
    saved = json.loads((root / 'assets' / 'image-variants.json').read_text())
    return {**drafts(root), **saved}


def referenced_keys(root):
    keys = set()
    for name in ('news', 'gallery'):
        for row in json.loads((root / 'assets' / f'{name}.json').read_text()):
            keys.update(row.get('images', []))
            if row.get('cover'): keys.add(row['cover'])
    for name in ('tici', 'hexin'):
        keys.update(row['file'] for row in json.loads((root / 'assets' / f'{name}.json').read_text()))
    return keys


def public_manifest(root):
    manifest = json.loads((root / 'assets' / 'image-variants.json').read_text())
    referenced = referenced_keys(root)
    # Imported historical resources remain available. Uploaded article/album
    # pictures become publishable only when a saved dataset references them.
    return {k: v for k, v in manifest.items() if not k.startswith('uploads/') or k in referenced}


def variant_paths(manifest):
    return {v[field] for v in manifest.values() for field in ('original', 'small', 'large', 'thumb') if v.get(field)}


def safe_path(base, relative):
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()): raise ValueError('图片路径不正确')
    return path


def promote_referenced(root):
    """Copy only saved references; never remove a draft or existing media file."""
    pending = drafts(root)
    path = root / 'assets' / 'image-variants.json'
    saved = json.loads(path.read_text())
    for key in referenced_keys(root):
        if key in saved or key not in pending: continue
        variant = pending[key]
        for relative in variant_paths({key: variant}):
            source = safe_path(draft_root(root), relative)
            destination = safe_path(root / 'assets', relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists(): shutil.copy2(source, destination)
        saved[key] = variant
    return saved
