# 代码说明

## 环境

Python >= 3.9。在仓库根目录执行：

```bash
pip install -r code/requirements.txt
```

> 如需 ILP 求解，优先使用 Gurobi（`gurobipy`），无 License 时自动回落 PuLP/HiGHS/CBC。

---

## 一键复现

从 `problem/` 附件表生成全部结果表与图表（在仓库根目录运行）：

```bash
# 完整流程
python code/run_all.py

# 快速验证（跳过重计算）
python code/run_all.py --quick

# 跳过敏感性分析
python code/run_all.py --skip-sens
```

**输出目录：**

| 路径 | 内容 |
|---|---|
| `code/results/tables/` | 结果表（xlsx）+ 所有 CSV |
| `code/results/figures/` | 全部图表（PNG） |

---

## 分步运行

```bash
# Step 1 数据预处理
python code/src/data/pipeline.py

# Step 2 Q1 求解
python code/src/q1/run_q1.py

# Step 3 Q2 求解
python code/src/q2/run_q2.py

# Step 4 Q3 求解
python code/src/q3/run_q3.py

# Step 5 敏感性
python code/src/sensitivity/run_all_sensitivity.py

# Step 6 绘图
python code/src/plotting/plot_Q1_<...>.py
# ……
```

---

## 目录结构

```
code/
├── run_all.py              # 一键复现入口
├── requirements.txt
├── README.md
├── data/
│   ├── raw/                # 附件表（只读）
│   └── processed/          # 清洗 / 派生表
├── results/
│   ├── tables/             # 结果表 + CSV
│   └── figures/            # 图表 PNG
├── src/
│   ├── data/               # 数据处理（pipeline.py, load_tables.py, constants.py）
│   ├── q1/                 # Q1 求解
│   ├── q2/                 # Q2 求解
│   ├── q3/                 # Q3 求解
│   ├── sensitivity/        # 敏感性扫描
│   └── plotting/           # 绘图脚本（一图一脚本）
├── notebooks/              # 探索性分析
└── tests/                  # 单元测试
```

---

## 编码与文件约定

- 附件表原始文件放在 `code/data/raw/`，不做任何手工修改
- 全部脚本统一编码 UTF-8；如附件表为 GBK 在 `load_tables.py` 中显式声明
- 中文输出图表需在 `matplotlib` 中设置中文字体（见 `plotting/_style.py`）
- 一图一脚本，文件名 `plot_<问题>_<内容>.py`，输出与脚本同名 PNG
