#!/usr/bin/env python3
"""一键复现脚本：从 problem/ 附件表生成全部结果表与图表。

运行环境：
  Python >= 3.9；依赖见 code/requirements.txt
  pip install -r code/requirements.txt

用法（从仓库根目录运行）：
  python code/run_all.py                # 完整流程
  python code/run_all.py --quick        # 跳过重计算
  python code/run_all.py --skip-sens    # 跳过敏感性分析

输出：
  code/results/tables/   全部结果表与 CSV
  code/results/figures/  全部图表（PNG）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = ROOT / "code"
SRC = CODE / "src"


def _run(label: str, script: Path, extra: list[str] | None = None) -> None:
    """Run a Python script as subprocess; exit on failure.

    所有脚本从仓库根目录 (ROOT) 运行，因为内部使用相对导入 (src.xxx).
    """
    if not script.exists():
        print(f"[跳过] {label}: 脚本不存在 {script}")
        return
    cmd = [sys.executable, str(script)] + (extra or [])
    print(f"\n{'='*60}")
    print(f"[{label}]  {script.relative_to(ROOT)}")
    print(f"{'='*60}")
    t0 = time.perf_counter()
    # 从 ROOT 运行，确保 `from src.xxx` 等相对导入正确
    result = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.perf_counter() - t0
    if result.returncode != 0:
        print(f"\n[错误] {label} 退出码 {result.returncode}，流程中止。", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"[完成] {label}  耗时 {elapsed:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="一键复现")
    parser.add_argument("--quick", action="store_true", help="跳过重计算（如 ILP / 敏感性）")
    parser.add_argument("--skip-sens", action="store_true", help="跳过敏感性分析")
    args = parser.parse_args()

    total_start = time.perf_counter()
    print("=" * 60)
    print("一键复现")
    print(f"ROOT: {ROOT}")
    print("=" * 60)

    # ── Step 1: 数据预处理 ─────────────────────────────────────────────────
    _run("Step 1  数据流水线", SRC / "data" / "pipeline.py")

    # ── Step 2: Q1 ────────────────────────────────────────────────────────
    _run("Step 2  Q1 求解", SRC / "q1" / "run_q1.py")

    # ── Step 3: Q2 ────────────────────────────────────────────────────────
    q2_extra = ["--quick"] if args.quick else []
    _run("Step 3  Q2 求解", SRC / "q2" / "run_q2.py", q2_extra)

    # ── Step 4: Q3 ────────────────────────────────────────────────────────
    _run("Step 4  Q3 求解", SRC / "q3" / "run_q3.py")

    # ── Step 5: 敏感性 ───────────────────────────────────────────────────
    if not args.quick and not args.skip_sens:
        _run("Step 5  敏感性分析", SRC / "sensitivity" / "run_all_sensitivity.py")
    else:
        print("\n[跳过] Step 5  敏感性分析")

    # ── Step 6: 绘图 ─────────────────────────────────────────────────────
    plotting_dir = SRC / "plotting"
    if plotting_dir.exists():
        for script in sorted(plotting_dir.glob("plot_*.py")):
            _run(f"Step 6  {script.stem}", script)

    total = time.perf_counter() - total_start
    print(f"\n{'='*60}")
    print(f"全部完成，总耗时 {total/60:.1f} 分钟")
    print(f"结果表：{CODE / 'results' / 'tables'}")
    print(f"图表：  {CODE / 'results' / 'figures'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
