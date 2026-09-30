"""Copy a built site into the public directory, replacing each file atomically."""
import os
import pathlib
import shutil
import sys
import tempfile
import time

root = pathlib.Path(__file__).resolve().parents[1]
target = pathlib.Path(sys.argv[1]).resolve()
if not target.is_absolute() or not (target / "index.html").is_file():
    raise SystemExit("Invalid public site directory")

backup = root / "admin" / "backups" / "published"
backup.mkdir(parents=True, exist_ok=True)
shutil.copy2(target / "index.html", backup / f"index-{time.strftime('%Y%m%d-%H%M%S')}.html")


def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file:
        with source.open("rb") as src:
            shutil.copyfileobj(src, file)
        temporary = pathlib.Path(file.name)
    temporary.chmod(0o644)
    os.replace(temporary, destination)


for name in ("data", "web", "files", "tici", "hexin", "people", "originals"):
    source_dir = root / "dist" / name
    if not source_dir.is_dir():
        continue
    for source in source_dir.rglob("*"):
        if source.is_file():
            atomic_copy(source, target / name / source.relative_to(source_dir))
atomic_copy(root / "dist" / "index.html", target / "index.html")

# Deleted entries must also disappear from their public detail URLs.
for folder in ("articles", "albums"):
    expected = {p.name for p in (root / "dist" / "data" / folder).glob("*.json")}
    for stale in (target / "data" / folder).glob("*.json"):
        if stale.name not in expected: stale.unlink()
