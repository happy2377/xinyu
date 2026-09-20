"""把心屿部署到 Hugging Face Space（在 GitHub Actions 里运行）。

GitHub Runner 可以访问 huggingface.co；本地网络受限时由 CI 代传。
"""
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

from huggingface_hub import HfApi

SPACE_ID = os.environ.get("SPACE_ID", "OU13866/xinyu")
TOKEN = os.environ["HF_TOKEN"]
MODELSCOPE_KEY = os.environ.get("MODELSCOPE_API_KEY", "")
ROOT = Path(__file__).resolve().parents[1]

IGNORE_DIRS = {"node_modules", ".next", "out", ".venv", "__pycache__", "data", ".git"}
IGNORE_FILES = {".env", ".env.local", ".env.production", ".DS_Store"}
IGNORE_SUFFIX = {".pyc", ".log"}

SPACE_README = """---
title: Xinyu
emoji: 💗
colorFrom: pink
colorTo: purple
sdk: docker
app_port: 3000
pinned: false
license: mit
---

# 心屿 Xinyu

AI 心理健康陪伴应用：共情对话、心理评估、情绪日记、语音引导训练、长期记忆、
RAG 知识问答、工具化 Agent 与效果周报。

> 仅用于学习研究，不构成医疗建议。免费 Space 存储为临时磁盘，重启后数据会重置。
"""


def copy_tree(src: Path, dst: Path) -> None:
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if any(part in IGNORE_DIRS for part in rel.parts):
            continue
        if path.name in IGNORE_FILES or path.suffix in IGNORE_SUFFIX:
            continue
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def build_stage() -> Path:
    stage = Path(tempfile.mkdtemp(prefix="xinyu-space-"))
    shutil.copy2(ROOT / "Dockerfile", stage / "Dockerfile")
    shutil.copy2(ROOT / ".dockerignore", stage / ".dockerignore")
    copy_tree(ROOT / "docker", stage / "docker")
    copy_tree(ROOT / "backend", stage / "backend")
    copy_tree(ROOT / "frontend", stage / "frontend")
    (stage / "README.md").write_text(SPACE_README, encoding="utf-8")
    return stage


def print_build_logs(api: HfApi) -> None:
    """尽力抓取 HF 构建日志，便于 CI 里直接看到失败原因。"""
    import httpx

    try:
        for kind in ("build", "container"):
            url = f"https://huggingface.co/api/spaces/{SPACE_ID}/logs/{kind}"
            resp = httpx.get(
                url,
                headers={"Authorization": f"Bearer {TOKEN}"},
                timeout=30,
                follow_redirects=True,
            )
            print(f"--- {kind} logs ({resp.status_code}) ---", flush=True)
            print(resp.text[:6000], flush=True)
    except Exception as exc:  # noqa: BLE001
        print("log fetch failed:", exc, flush=True)


def main() -> int:
    api = HfApi(token=TOKEN)
    print(f"creating space {SPACE_ID} ...", flush=True)
    api.create_repo(
        repo_id=SPACE_ID,
        repo_type="space",
        space_sdk="docker",
        private=False,
        exist_ok=True,
    )

    if MODELSCOPE_KEY:
        api.add_space_secret(SPACE_ID, "MODELSCOPE_API_KEY", MODELSCOPE_KEY, token=TOKEN)
    api.add_space_secret(SPACE_ID, "SECRET_KEY", uuid.uuid4().hex * 2, token=TOKEN)
    api.add_space_variable(
        SPACE_ID, "DATABASE_URL", "sqlite:////data/xinyu.db", token=TOKEN
    )

    stage = build_stage()
    print(f"uploading {sum(1 for _ in stage.rglob('*'))} entries ...", flush=True)
    api.upload_folder(
        repo_id=SPACE_ID,
        repo_type="space",
        folder_path=str(stage),
        commit_message="deploy: xinyu full-stack space",
        token=TOKEN,
    )

    for _ in range(120):  # 最多等待 20 分钟
        runtime = api.get_space_runtime(SPACE_ID, token=TOKEN)
        stage_name = runtime.stage
        print("space stage:", stage_name, flush=True)
        if stage_name == "RUNNING":
            print(f"deployed: https://huggingface.co/spaces/{SPACE_ID}", flush=True)
            return 0
        if stage_name in {"BUILD_ERROR", "CONFIG_ERROR", "RUNTIME_ERROR"}:
            print_build_logs(api)
            return 1
        time.sleep(10)

    print("timeout waiting for space", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
