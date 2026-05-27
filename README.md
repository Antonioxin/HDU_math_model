# 数模竞赛工作目录模板

> 基于 2026 长三角赛题 A 的完整流程沉淀，**直接拷贝本目录用作下一次比赛脚手架**。
>
> 拷贝后逐步替换 `problem/`、`code/data/raw/`、各 `*.md`、`*.tex` 中的占位内容即可。

## 目录结构

```
<比赛名>/
├── problem/          赛题原文与附件（比赛开始后放入；只读）
├── model/            建模手主导：假设、推导草稿、技术路线、敏感性 / 边界设计
├── code/             代码手主导：Python 代码、数据、运行结果
├── paper/            论文手主导：LaTeX 源文件、插图、参考文献
└── assets/           全员共享：参考资料、讨论记录、模型检查清单
```

## 三人分工

| 角色 | 主要目录 | 说明 |
|------|----------|------|
| 建模手 | `model/` | 写假设清单、符号体系、数学推导草稿；维护各问 `formulation/*.md`；配合论文手撰写 `paper/sections/3_model.tex` |
| 代码手 | `code/` | 编写 Python 脚本与 Jupyter 分析；保证 `code/results/figures/` 图表在提交前完整产出 |
| 论文手 | `paper/` | 维护 `main.tex` 与编译；整合建模手草稿与代码手图表排版成文 |

## 工作流约定

### 数据约定
- `code/data/raw/`：**只读**，原始数据绝不直接修改
- `code/data/processed/`：所有预处理结果写入此处，方便复现

### 图表流转
- 代码手将图表输出至 `code/results/figures/`
- 论文手将所需图表复制至 `paper/figures/`，再在 `.tex` 中引用

### 单一信息源（Single Source of Truth）
- **符号与假设**：`model/assumptions.md`（修改后须同步代码手命名、论文手 `2_assumptions.tex`）
- **参数数值**：`model/参数总表.md`
- **跨问接口**：`model/模型定位说明.md`
- **一致性核查**：交稿前用 `paper/一致性核查表.md` 逐项核对

### Git 提交规范
见 `CONTRIBUTING.md`，简表如下：

```
[建模] 完成问题一假设清单
[代码] 问题二：添加 GA 求解脚本
[论文] 完成第三节模型描述初稿
[数据] 补充原始数据集
[图表] / [结果] / [文档] / [修复] / [结构]
```

### 编译论文
```bash
cd paper
latexmk -xelatex -outdir=build main.tex
# 或：make watch  （监听模式，保存即重编）
```

### 一键复现代码
```bash
pip install -r code/requirements.txt
python code/run_all.py            # 完整流程
python code/run_all.py --quick    # 跳过重计算
```

## 重要提醒

- 禁止将大体积数据文件（>10 MB）直接 `git add`，使用 `.gitignore` 或 Git LFS
- `paper/build/` 目录已由 `.gitignore` 排除，不要手动 `git add` 编译产物
- 比赛结束前请确保在本地保留完整备份

## 复用 Checklist（新比赛开始时）

- [ ] 将本模板整目录拷贝并改名为新比赛名
- [ ] 清空 `problem/`、`code/data/raw/`、`code/results/`、`paper/build/`、`paper/figures/` 中的占位内容
- [ ] 替换 `paper/sections/abstract.tex` 顶部参赛信息栏
- [ ] 替换 `paper/main.tex` 顶部注释中的提交日期 / 文件命名规则
- [ ] 根据新赛题问题数调整 `code/src/q*/` 子目录与 `model/formulation/Q*_*.md`
- [ ] 用真实数据填充 `model/assumptions.md` 与 `model/参数总表.md`
- [ ] 初始化 git：`git init && git add . && git commit -m "[结构] 初始化模板"`
