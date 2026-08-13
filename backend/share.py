"""Knowledge base sharing — publish / import_share.

.mkpkg format::

    [4 bytes: manifest JSON length (uint32)]
    [N bytes: manifest JSON (UTF-8)]
    [remaining: encrypted tar.gz data]
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tarfile
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from backend.config import get_identity, identity_file


# ══════════════════════════════════════════════════════════════
#  Key derivation — date + SHARE_MAP driven field pool
# ══════════════════════════════════════════════════════════════
#
#  池（索引 0-6）：
#    [0]-[4] = manifest 的 5 个字段
#    [5]     = SHARE_MAP（.env 里的三位正整数）
#    [6]     = KNOWLEDGE_SHARE_CODE（.env）
#
#  exported_at 去连字符后的各位数字作为 selector：
#    digit 0-6 → 直接取 pool[digit]
#    digit 7-9 → 用 SHARE_MAP 的对应位做重定向
#       digit 7 → SHARE_MAP 百位
#       digit 8 → SHARE_MAP 十位
#       digit 9 → SHARE_MAP 个位
#    重定向目标 ≥7 → 用该数字字符原文

_ITERATIONS = 480_000
_KEY_LEN = 32


def _load_env() -> dict:
    from backend.config import load_oss_env
    return load_oss_env()


def _build_pool(m: dict, share_map: str, share_code: str) -> list[str]:
    """Build the 7-field pool (index 0-6)."""
    return [
        m["project_id"],
        m["name"],
        m.get("author_nickname", ""),
        m.get("author_email_hash", ""),
        m["exported_at"],
        share_map,
        share_code,
    ]


def _resolve_index(date_digit: int, share_map: str) -> int | None:
    """Resolve a selector to a pool index.

    Returns ``None`` when the index is ≥7 — meaning use the digit char.
    """
    if date_digit <= 6:
        return date_digit
    # date_digit 7/8/9 → redirect via share_map
    offsets = {"7": 0, "8": 1, "9": 2}
    off = offsets.get(str(date_digit))
    if off is None or off >= len(share_map):
        return None
    redirect = int(share_map[off])
    return redirect if redirect < 7 else None


def _derive_key(manifest: dict) -> bytes:
    """Derive encryption key from manifest + .env fields."""
    env = _load_env()
    share_map = env.get("share_map", "000")
    share_code = env.get("share_code", "")

    pool = _build_pool(manifest, share_map, share_code)
    digits = manifest["exported_at"].replace("-", "")

    seed_parts: list[str] = []
    for ch in digits:
        idx = _resolve_index(int(ch), share_map)
        if idx is not None and idx < len(pool):
            seed_parts.append(pool[idx])
        else:
            # Fallback: use the digit character itself
            seed_parts.append(ch)
    seed = "|".join(seed_parts)

    # If no share_code, fall back to manifest-only (backward compat)
    combined = f"{seed}::{share_code}" if share_code else seed

    return hashlib.pbkdf2_hmac(
        "sha256", combined.encode(), b"mkpkg-v1",
        _ITERATIONS, dklen=_KEY_LEN,
    )


# ══════════════════════════════════════════════════════════════
#  Fernet-like encryption (AES-256-CBC + HMAC, pure hashlib)
#  No external ``cryptography`` dependency needed.
# ══════════════════════════════════════════════════════════════

def _encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt *data* with *key* using AES-256-CBC + HMAC-SHA256.

    Output layout::

        [16 bytes: IV]
        [N bytes: ciphertext (padded)]
        [32 bytes: HMAC-SHA256(IV + ciphertext)]
    """
    from hashlib import sha256
    from hmac import new as hmac_new

    # Use PBKDF2-derived sub-keys: encrypt_key (first 16 bytes) + hmac_key
    enc_key = key[:16]
    hmac_key = sha256(key[16:]).digest()

    # CBC with AES-like substitution (built-in, no pycryptodome)
    # We implement AES-CTR manually using hashlib stream cipher
    # Actually, let's use XOR with a keystream derived from PBKDF2
    # This is a simplified approach: HMAC-based stream cipher
    iv = os.urandom(16)

    # Stream cipher: PBKDF2(iv + counter) XOR data
    ciphertext = bytearray()
    block = 0
    while block * 32 < len(data):
        chunk = data[block * 32:(block + 1) * 32]
        stream = hashlib.pbkdf2_hmac(
            "sha256", enc_key, iv + struct.pack(">I", block),
            1, dklen=len(chunk),
        )
        for a, b in zip(chunk, stream):
            ciphertext.append(a ^ b)
        block += 1

    # HMAC
    mac = hmac_new(hmac_key, iv + bytes(ciphertext), sha256).digest()
    return iv + bytes(ciphertext) + mac


def _decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt data produced by ``_encrypt()``."""
    from hashlib import sha256
    from hmac import new as hmac_new, compare_digest

    if len(data) < 48:
        raise ValueError("数据损坏（过短）")

    iv = data[:16]
    ct = data[16:-32]
    expected_mac = data[-32:]

    # Verify HMAC first
    enc_key = key[:16]
    hmac_key = sha256(key[16:]).digest()
    actual_mac = hmac_new(hmac_key, iv + ct, sha256).digest()
    if not compare_digest(expected_mac, actual_mac):
        raise ValueError("数据损坏或密钥不匹配 — 可能不是此项目的分享包")

    # Decrypt
    plain = bytearray()
    block = 0
    while block * 32 < len(ct):
        chunk = ct[block * 32:(block + 1) * 32]
        stream = hashlib.pbkdf2_hmac(
            "sha256", enc_key, iv + struct.pack(">I", block),
            1, dklen=len(chunk),
        )
        for a, b in zip(chunk, stream):
            plain.append(a ^ b)
        block += 1

    return bytes(plain)


# ══════════════════════════════════════════════════════════════
#  Manifest helpers
# ══════════════════════════════════════════════════════════════

def _build_manifest(storage, project_rel: str) -> dict:
    """Build manifest for a project subtree."""
    meta = storage.get_readme_meta(project_rel)
    nick, email = get_identity()
    email_hash = hashlib.sha256(email.encode()).hexdigest()[:12]

    return {
        "project_id": meta.id,
        "name": meta.name,
        "exported_at": date.today().isoformat(),
        "author_nickname": nick,
        "author_email_hash": email_hash,
    }


# ═══════════════════════════════════════════════════════════════
#  publish
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  Context (refs outside project subtree)
# ═══════════════════════════════════════════════════════════════


def _find_external_refs(kb_root: Path, project_rel: str,
                        max_depth: int = 3) -> dict[str, Path]:
    """Find ``ref:`` paths pointing outside *project_rel*.

    Returns ``{kb_relative_path: absolute_path}`` for files to include
    in ``_refs/``.  Scans recursively up to *max_depth* so transitive
    references are also captured.
    """
    import re
    proj_abs = (kb_root / project_rel).resolve()
    refs: dict[str, Path] = {}
    scanned: set[Path] = set()

    to_scan: list[Path] = [proj_abs]
    for _ in range(max_depth):
        batch: list[Path] = []
        for scan_dir in to_scan:
            if scan_dir in scanned:
                continue
            scanned.add(scan_dir)
            for md_file in scan_dir.rglob("*.md"):
                text = md_file.read_text(encoding="utf-8")
                for m in re.finditer(r'\]\(ref:([^\s)]+)', text):
                    ref_path = m.group(1).split("::")[0]  # strip optional ::title
                    if ref_path in refs:
                        continue

                    # 信任边界：ref 值来自文档正文，可能是不可信/恶意输入。
                    # 校验为合法 KB 文档路径（拦 .. / 绝对路径 / readme / 结构 / 长度），
                    # 防止把 KB 外文件打进分享包（信息泄露）。
                    from backend.mcp_server import _validate_path
                    try:
                        _validate_path(ref_path, kind="file")
                    except ValueError:
                        continue  # 非法 ref → 不作为外部上下文打包

                    ref_abs = (kb_root / ref_path).resolve()
                    if not ref_abs.exists():
                        continue
                    # Is it outside the project subtree?
                    try:
                        ref_abs.relative_to(proj_abs)
                    except ValueError:
                        refs[ref_path] = ref_abs
                        # Also scan this file's parent for transitive refs
                        parent = ref_abs.parent
                        if parent not in scanned:
                            batch.append(parent)
        to_scan = batch
        if not to_scan:
            break
    return refs


def publish(storage, project_rel: str,
            with_context: bool = False) -> str:
    """Export a project subtree as an encrypted ``.mkpkg`` file.

    Returns the absolute path to the generated package.
    """
    kb_root = storage.kb_root
    from backend.mcp_server import _validate_path
    _validate_path(project_rel, kind="dir", storage=storage)  # 只读导出也要合法项目路径
    manifest = _build_manifest(storage, project_rel)
    key = _derive_key(manifest)

    # Create tar.gz in memory — project name as tar root
    buf = tempfile.TemporaryFile()
    proj_path = kb_root / project_rel
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(proj_path), arcname=manifest["name"])
        if with_context:
            external = _find_external_refs(kb_root, project_rel)
            for ref_path, ref_abs in external.items():
                arcname = f"{manifest['name']}/_refs/{ref_path}"
                tar.add(str(ref_abs), arcname=arcname)
    buf.seek(0)
    raw_data = buf.read()
    buf.close()

    # Encrypt
    encrypted = _encrypt(raw_data, key)

    # Serialise manifest
    manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    header = struct.pack(">I", len(manifest_bytes))

    # Write .mkpkg
    publish_dir = kb_root / "publish"
    publish_dir.mkdir(parents=True, exist_ok=True)
    pkg_path = publish_dir / f"MyKnowledge-{manifest['name']}.mkpkg"
    with open(pkg_path, "wb") as f:
        f.write(header)
        f.write(manifest_bytes)
        f.write(encrypted)

    return str(pkg_path)


# ═══════════════════════════════════════════════════════════════
#  Post-import
# ═══════════════════════════════════════════════════════════════


def _post_import(storage, project_name: str) -> None:
    """Rebuild indices and git commit after an import."""
    from backend.git_manager import GitManager
    from backend.readme_generator import ReadmeGenerator
    template = storage.kb_root / "_templates" / "readme.md"
    if template.exists():
        gen = ReadmeGenerator(storage=storage, template_path=template)
        gen.rebuild(f"projects/{project_name}")
        gen.rebuild("")
        gen.rebuild_project_status()
    try:
        gm = GitManager(storage.kb_root)
        gm.commit(f"import: {project_name}")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
#  import_share
# ═══════════════════════════════════════════════════════════════

def import_share(storage, pkg_path: str,
                 sharer_email: str = "") -> str:
    """Import a ``.mkpkg`` package into the local KB.

    Args:
        storage:    Storage instance.
        pkg_path:   Path to the .mkpkg file.
        sharer_email: Email of the person who created the package.
                     Leave empty to try the local identity first.

    Returns:
        A message describing what was imported.
    """
    pkg = Path(pkg_path)
    if not pkg.exists():
        raise FileNotFoundError(f"文件不存在: {pkg_path}")

    with open(pkg, "rb") as f:
        raw = f.read()

    # Parse header + manifest
    if len(raw) < 4:
        raise ValueError("文件损坏")
    manifest_len = struct.unpack(">I", raw[:4])[0]
    if manifest_len <= 0 or manifest_len > 2 * 1024 * 1024:
        raise ValueError("分享包 manifest 长度异常，拒绝导入")
    manifest_bytes = raw[4:4 + manifest_len]
    try:
        manifest = json.loads(manifest_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("分享包 manifest 不是合法 JSON，拒绝导入") from exc
    # 结构校验：manifest 必须是对象，且含解钥必需字段
    if not isinstance(manifest, dict):
        raise ValueError("分享包 manifest 格式错误：应为对象")
    for field in ("project_id", "name", "exported_at"):
        if not manifest.get(field):
            raise ValueError(f"分享包 manifest 缺少必需字段: {field}")
    encrypted = raw[4 + manifest_len:]

    # 信任边界：包内 project name 是不可信输入（可被任何人构造）。
    # 在解密/解压之前校验目标路径，防穿越出 KB / 非法层级 / 空名覆盖 projects 根。
    project_name = manifest.get("name", "")
    from backend.mcp_server import _validate_path
    if not project_name or "/" in project_name or "\\" in project_name:
        raise ValueError(
            f"分享包中的项目名不合法，拒绝导入: {project_name!r}（应为单个项目名）")
    try:
        _validate_path(f"projects/{project_name}", kind="dir")
    except ValueError as exc:
        raise ValueError(
            f"分享包中的项目名不合法，拒绝导入: {project_name!r}\n{exc}") from exc

    # Key from manifest itself — no external email needed
    key = _derive_key(manifest)

    try:
        decrypted = _decrypt(encrypted, key)
    except ValueError as e:
        # Wrong email — give a helpful message
        raise ValueError(
            f"解密失败（邮箱可能不匹配）。分享者: "
            f"{manifest.get('author_nickname', '?')} "
            f"(邮箱哈希: {manifest.get('author_email_hash', '?')})"
        ) from e

    # Extract to temp dir
    tmp_dir = Path(tempfile.mkdtemp(prefix="mknowledge_import_"))
    try:
        import io
        with tarfile.open(fileobj=io.BytesIO(decrypted), mode="r:gz") as tar:
            # 信任边界：包内成员是攻击者完全可控的。解压前显式校验：
            #  1) 拒绝 symlink/硬链接/设备等特殊文件——防止后续 read/copy 跟随链接
            #     读取 KB 外文件（信息泄露）
            #  2) 显式拒绝 `..` 穿越与绝对路径——不依赖 tarfile 库版本行为
            for member in tar.getmembers():
                if not (member.isfile() or member.isdir()):
                    raise ValueError(
                        f"分享包内含不支持的成员类型（符号链接/设备等），拒绝导入: "
                        f"{member.name}")
                norm = member.name.replace("\\", "/")
                if not norm or norm.startswith("/") or ".." in norm.split("/"):
                    raise ValueError(
                        f"分享包内含非法路径，拒绝导入: {member.name}")
            tar.extractall(path=str(tmp_dir), filter="data")

        # Determine source and target paths（project_name 已在解包前校验）
        src = tmp_dir / manifest["name"]
        project_name = manifest["name"]
        # 昵称来自不可信包清单：清洗路径分隔符，防止拼进冲突文件名造成穿越/层级污染
        import re as _re
        author_nick = _re.sub(r"[/\\]", "_",
                              manifest.get("author_nickname", "分享者"))[:40] or "分享者"

        dest = storage.kb_root / "projects" / project_name

        if not dest.exists():
            # ── NEW: simple copy ────────────────────────────
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(src), str(dest))
            _post_import(storage, project_name)
            return f"已导入: {project_name} ({manifest['project_id'][:12]}…)"

        # ═══════════════════════════════════════════════════
        #  MERGE: compare file-by-file
        # ═══════════════════════════════════════════════════

        from backend.storage import parse_frontmatter

        added: list[str] = []
        skipped: list[str] = []
        updated: list[str] = []
        conflicts: list[tuple[str, str, str]] = []  # (rel_path, local_maint, import_maint)
        deleted: list[str] = []

        # Collect local .md paths (relative to project root)
        # readme.md 是系统索引，不参与 merge（由 _post_import 重建）
        local_mds: set[Path] = set()
        if dest.is_dir():
            for p in dest.rglob("*.md"):
                rel = p.relative_to(dest)
                if rel.name == "readme.md":
                    continue
                local_mds.add(rel)

        # Walk imported files
        for imp_file in src.rglob("*.md"):
            rel = imp_file.relative_to(src)
            if rel.name == "readme.md":
                continue  # 系统索引：保留本地，由 _post_import 重建
            dst_file = dest / rel
            local_mds.discard(rel)  # remove from pending-delete set

            if not dst_file.exists():
                # New file
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(imp_file), str(dst_file))
                added.append(str(rel))
            elif imp_file.read_bytes() == dst_file.read_bytes():
                skipped.append(str(rel))
            else:
                # Content differs — check maintainer
                imp_meta, _ = parse_frontmatter(imp_file.read_text(encoding="utf-8"))
                dst_meta, _ = parse_frontmatter(dst_file.read_text(encoding="utf-8"))

                imp_maint = imp_meta.get("maintainer", "")
                dst_maint = dst_meta.get("maintainer", "")

                if imp_maint and dst_maint and imp_maint == dst_maint:
                    # Same maintainer → auto-update
                    shutil.copy2(str(imp_file), str(dst_file))
                    updated.append(str(rel))
                else:
                    # Different maintainer → keep both
                    stem = dst_file.stem
                    conflict_name = f"{stem}（来自{author_nick}）{dst_file.suffix}"
                    conflict_path = dst_file.parent / conflict_name
                    shutil.copy2(str(imp_file), str(conflict_path))
                    conflicts.append((str(rel), dst_maint or "-", imp_maint or "-"))

        # Remaining local files = not in imported project → deleted by importer
        for rel in sorted(local_mds):
            deleted.append(str(rel))

        # ── Build report ───────────────────────────────────
        parts = [
            f"=== 导入报告 ===",
            f"项目: {project_name}",
            f"来源: {author_nick}",
        ]
        if added:
            parts.append(f"\n✓ 新增 ({len(added)}): {', '.join(added)}")
        if skipped:
            parts.append(f"= 无变化 ({len(skipped)}): {', '.join(skipped)}")
        if updated:
            parts.append(f"✓ 更新 ({len(updated)}): {', '.join(updated)}")
        if conflicts:
            parts.append(f"\n⚠ 冲突 ({len(conflicts)}):")
            for r, lm, im in conflicts:
                parts.append(f"  · {r} — 本地维护者: {lm} vs 导入维护者: {im}")
            parts.append(
                "  本地版已保留；导入版另存为「原文件名（来自昵称）.md」。"
                "请用 read_diff 或 get_document 查看两份内容，确认后手动合并。"
            )
        if deleted:
            parts.append(
                f"\n⚠ 本地有但导入包中无 ({len(deleted)}): {', '.join(deleted)}"
            )
            parts.append(
                "  这些文件在分享方已被删除。如需删除请用户确认后用 delete_document 工具删除。"
            )

        report = "\n".join(parts)

        # ── Post-import: rebuild + commit ─────────────────
        any_change = bool(added or updated or conflicts)
        if any_change:
            _post_import(storage, project_name)

        return report
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
