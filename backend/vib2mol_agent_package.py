"""Install the supplied Agent code beside upstream Vib2Mol without unpacking run logs."""
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

ARCHIVE_SHA256 = '690107b695ac8f3d1a9fe2f23a326542a2e71e57d2fdd4fcd6ad9aa4196f0e76'
RUNTIME_ARCHIVE_SHA256 = '7b512455e34a6ab1218c54611320d11b5b5b7aaf25018db351b951580737867f'
MANIFEST = '.ramancloud-manifest.json'


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def package_hash(root):
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*'), key=lambda value: value.relative_to(root).as_posix()):
        if path.is_file() and path.name != MANIFEST and '__pycache__' not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b'\0')
            digest.update(path.read_bytes())
    return digest.hexdigest()


def installed_agent(source):
    root = Path(source) / 'vib2mol_agent'
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
        if manifest.get('archive_sha256') == ARCHIVE_SHA256 and (root / 'core/agent.py').exists():
            return manifest
    except (OSError, ValueError):
        pass
    return None


def install_agent(archive, source):
    archive, source = Path(archive), Path(source).resolve()
    if not (source / 'models/vib2mol.py').is_file():
        raise ValueError('请先安装官方 Vib2Mol 源码。')
    supplied_sha256 = file_hash(archive)
    if supplied_sha256 not in {ARCHIVE_SHA256, RUNTIME_ARCHIVE_SHA256}:
        raise ValueError('压缩包版本与已验证的 Agent 版本不一致，请先检查新版接口。')
    selected = []
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            path = PurePosixPath(member.filename)
            target = (source / Path(*path.parts)).resolve()
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'vib2mol_agent' or source not in target.parents:
                raise ValueError('压缩包存在越界路径。')
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('压缩包中不能包含符号链接。')
            if member.is_dir() or '__pycache__' in path.parts or 'runs' in path.parts or 'useful' in path.parts:
                continue
            if path.suffix.lower() not in ('.py', '.json', '.jsonl', '.md', '.txt', '.yaml', '.yml', '.toml'):
                continue
            content = zipped.read(member)
            if target.exists() and target.read_bytes() != content:
                raise ValueError('保留本地修改，未覆盖文件：' + str(target))
            selected.append((target, content))
        for target, content in selected:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(content)
    root = source / 'vib2mol_agent'
    manifest = dict(archive_sha256=ARCHIVE_SHA256, supplied_archive_sha256=supplied_sha256,
                    package_sha256=package_hash(root), files=len(selected),
                    omitted='runs, PDF and other media; evaluation Python helpers retained for runtime imports')
    (root / MANIFEST).write_text(json.dumps(manifest), encoding='utf-8')
    return manifest
