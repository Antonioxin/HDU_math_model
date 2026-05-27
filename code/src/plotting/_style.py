"""matplotlib 通用样式。

在每个 plot_*.py 顶部 `from _style import apply_style; apply_style()`。
"""
from __future__ import annotations

import matplotlib as mpl


def apply_style() -> None:
    mpl.rcParams.update({
        "font.family": "sans-serif",
        # macOS / Windows 跨平台中文回退
        "font.sans-serif": ["Heiti SC", "PingFang SC", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
    })
