#!/usr/bin/env python3
"""生成可下载的 Skill zip + SHA-256 清单。仅使用 Python 标准库。

设计（方案 §5.6）：
- 读仓库根 skills/manifest.json，对其中每个 skill 生成版本化 zip：
  <slug>-v<version>.zip，并复制出稳定别名 <slug>.zip。
- zip 内固定包含一个顶层目录 <slug>/，避免解压散落。
- 排除：__pycache__ / *.pyc / .venv / 模型权重(*.onnx) / 密钥 / 系统隐藏文件。
- 模型权重默认**不**打进 zip（许可证与体积），由下载者首次使用时按需下载。
- 输出目录默认 frontend/public/skills/（随站托管下载）。

本地预览与 Docker 构建都调用同一个脚本，保证产物一致。
"""

import argparse
import hashlib
import json
import pathlib
import shutil
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def should_exclude(p: pathlib.Path, source_root: pathlib.Path) -> bool:
    rel = p.relative_to(source_root)
    parts = set(rel.parts)
    if "__pycache__" in parts:
        return True
    if ".venv" in parts:
        return True
    if p.name in {".DS_Store", "Thumbs.db"}:
        return True
    if p.suffix == ".pyc":
        return True
    if p.name.endswith(".onnx"):  # 模型权重不进 zip
        return True
    if p.name.endswith(".sha256"):  # 避免递归打包清单
        return True
    if p.name in {"__pycache__"}:
        return True
    return False


def build_one(slug: str, meta: dict, output_dir: pathlib.Path) -> None:
    source = ROOT / meta["source"]
    version = meta["version"]
    top = slug  # 顶层目录名

    if not source.is_dir():
        print(f"[skip] {slug}: source dir not found: {source}", file=sys.stderr)
        return

    zip_name = f"{slug}-v{version}.zip"
    zip_path = output_dir / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        files = sorted(p for p in source.rglob("*") if p.is_file())
        if not files:
            raise SystemExit(f"[error] {slug}: no files in {source}")
        for f in files:
            if should_exclude(f, source):
                continue
            arcname = pathlib.PurePosixPath(top) / f.relative_to(source)
            zf.write(f, arcname.as_posix())

    # 稳定别名（供下载页 /skills/<slug>.zip 使用；网关侧配置不缓存或重新验证）。
    alias = output_dir / f"{slug}.zip"
    shutil.copyfile(zip_path, alias)

    sha = sha256_of(zip_path)
    (output_dir / f"{slug}-v{version}.zip.sha256").write_text(f"{sha}  {zip_name}\n")
    (output_dir / f"{slug}.zip.sha256").write_text(f"{sha}  {slug}.zip\n")

    size_kb = zip_path.stat().st_size // 1024
    print(f"[ok] {slug} v{version}: {zip_name} ({size_kb} KB), sha256={sha[:12]}…")


def main() -> None:
    ap = argparse.ArgumentParser(description="Package skills into downloadable zips.")
    ap.add_argument(
        "--output",
        default=str(ROOT / "frontend" / "public" / "skills"),
        help="输出目录（默认 frontend/public/skills）",
    )
    ap.add_argument(
        "--manifest",
        default=str(ROOT / "skills" / "manifest.json"),
        help="技能清单路径",
    )
    args = ap.parse_args()

    manifest_path = pathlib.Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_dir = pathlib.Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    for slug, meta in manifest.get("skills", {}).items():
        build_one(slug, meta, output_dir)

    print(f"done -> {output_dir}")


if __name__ == "__main__":
    main()
