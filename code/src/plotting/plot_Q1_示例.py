"""Q1 绘图示例。命名规范：plot_Q{n}_<内容>.py，一图一脚本。"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _style import apply_style  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
FIG_DIR = ROOT / "code" / "results" / "figures"


def main() -> None:
    apply_style()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.set_title("Q1 示例图（替换为真实内容）")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    out = FIG_DIR / "Q1_示例.png"
    fig.savefig(out)
    print(f"[plot] saved {out}")


if __name__ == "__main__":
    main()
