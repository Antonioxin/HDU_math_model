# 模型假设与符号体系

> **维护者**：建模手。本文件是全文符号与假设的**唯一来源**（single source of truth），各 `formulation/*.md`、`参数总表.md`、`paper/sections/2_assumptions.tex` 均以此为准。
>
> 修改本文件后，必须同步通知代码手（修订 `code/src` 中变量命名）与论文手（同步 `paper/`）。

---

## 1. 集合与索引

| 符号 | 含义 | 规模 / 备注 |
|------|------|-------------|
| $\mathcal{T}_{\text{hist}}$ | 历史观测期 | 附件1：$\{0,20,\dots,3500\}$ 天；附件2：$\{0,1,\dots,1800\}$ 天 |
| $\mathcal{T}_{\text{pred}}$ | 预测期（待外推） | $t > 1800$ 天（附件2 之后） |
| $\mathcal{B}$ | 轴承全集 | 15 个（XJTU-SY），$\|\mathcal{B}\|=15$ |
| $\mathcal{B}^{\text{out}}$ | 外圈失效子集（与飞轮可比） | 9 个：Bearing 1\_1/1\_2/1\_3、2\_2/2\_4/2\_5、3\_1/3\_2/3\_5 |
| $\mathcal{C}$ | 工况集 | $\{C_1,C_2,C_3\}$，对应转速 2100/2250/2400 rpm、径向力 12/11/10 kN |
| $\mathcal{F}$ | 振动特征集 | 11 项（时域 5 + 频域 3 + 时频 3） |
| $\mathcal{S}$ | 健康阶段集 | $\{H,D,F\}$ = 健康 / 退化 / 衰退 |
| $\mathcal{L}$ | 预警等级集 | $\{L_0,L_1,L_2,L_3\}$ = 正常 / 关注 / 告警 / 紧急 |
| $i,j$ | 通用索引 |  |
| $t$ | 时间索引（天 / 分钟，依上下文） |  |
| $b\in\mathcal{B}$ | 轴承索引 |  |
| $k$ | 特征索引，$k\in\{1,\dots,\|\mathcal{F}\|\}$ |  |

---

## 2. 已知参数（题面给定）

| 符号 | 含义 | 单位 | 来源 |
|------|------|------|------|
| $J$ | 飞轮转动惯量 | $\text{kg}\cdot\text{m}^2$ | 题面 §1.2 / 文献 [2] 表 3-1 |
| $K_T$ | 电机转矩常数 | $\text{N}\cdot\text{m}/\text{A}$ | 题面 §1.2 |
| $\omega_0$ | 额定转速 | rpm | 题面 §1.2 |
| $i_{\max}$ | 飞轮最大输出电流 | A | 题面 §1.2 |
| $f_s^{\text{vib}}$ | XJTU-SY 振动采样率 | Hz | XJTU-SY ReadMe |
| $L_{\text{rec}}$ | 单次振动文件采样点数 | 个 | XJTU-SY ReadMe |
| $\Delta t_1$ | 附件1 采样间隔 | 天 | 附件1 day 列差分 |
| $\Delta t_2$ | 附件2 采样间隔 | 天 | 附件2 day 列差分 |
| $\Delta t_{\text{vib}}$ | 振动文件采集间隔 | 秒 | XJTU-SY 约定 |

数值见 [`参数总表.md`](参数总表.md)。

---

## 3. 决策变量

| 符号 | 含义 | 类型 / 范围 | 所属问题 |
|------|------|-------------|---------|
| $\hat{\boldsymbol\theta}_A=(i_0,\alpha,\beta,\sigma_\varepsilon^2)$ | 物理指数退化模型参数（飞轮） | 连续，$\beta>0$ | Q1 |
| $\hat{\boldsymbol\theta}_B=(\alpha,\beta,\sigma_B^2)$ | Λ-时间 Wiener 退化过程参数（飞轮）；$(\alpha,\beta)$ 共享自模型 A，仅 $\sigma_B^2$ 独立估计 | 连续，$\sigma_B^2>0$ | Q1 |
| $\hat S_b(t)\in\mathcal{S}$ | 设备 $b$ 在时刻 $t$ 的健康阶段标签 | 离散 3 类 | Q1/Q2/Q3 |
| $\widehat{\text{RUL}}(t)$ | 时刻 $t$ 处的剩余寿命点估计 | 连续，$\ge 0$，单位：天 | Q1/Q3 |
| $\widehat{\text{RUL}}^{(\alpha)}(t)$ | RUL 的 $\alpha$ 分位（默认 $\alpha\in\{0.025,0.5,0.975\}$） | 连续 | Q1/Q3 |
| $\hat S_F\in\{0,1\}^{\|\mathcal{F}\|}$ | 特征选择指示向量 | 0/1 | Q2 |
| $\text{HI}_b(t)\in[0,1]$ | 健康指数（min-max 归一化后） | 连续 | Q2 |
| $\hat L(t)\in\mathcal{L}$ | 预警等级 | 离散 4 级 | Q3 |
| $\lambda\in[0,1]$ | 迁移权重 | 连续 | Q3 |

---

## 4. 派生量

| 符号 | 定义式 | 含义 |
|------|--------|------|
| $\Delta i_t$ | $i_t - i_t^{\text{theo}}$ | 残差电流（去基线后的退化信号） |
| $\Delta i_F$ | $i_F - i_0$ | 从初始到失效阈值的总电流增量 |
| $\tau_b(t)$ | $t / T^{\text{EOL}}_b$ | 归一化寿命（用于跨域对齐），$\tau\in[0,1]$ |
| $T^{\text{EOL}}_b$ | $\inf\{t: i_t \ge i_F\}$（飞轮）或 $\inf\{t:\text{HI}_t\ge\text{HI}_F\}$（轴承） | 端到端寿命 |
| $D(t)$ | $i_t - i_0$ | 电流退化增量（Λ-时间 Wiener 退化信号） |
| $\Lambda(t)$ | $\alpha(e^{\beta t}-1)$ | 累积退化均值 = 运行时间（operational time），$\Lambda^{-1}(s)=\frac1\beta\ln(1+s/\alpha)$ |
| $\sigma_B^2$ | $\frac{1}{K-1}\sum_k(\Delta r_k)^2/\Delta\Lambda_k$，$r_k=D_k-\Lambda(t_k)$ | Λ-时间 Wiener 扩散系数 |
| $\text{Mon}(F)$ | $\big|\#(\Delta F>0)-\#(\Delta F<0)\big|/(K-1)$ | 特征单调性指标 |
| $\text{Trd}(F)$ | $\big|\rho_{\text{Spearman}}(F,t)\big|$ | 特征趋势性指标 |
| $\text{Rob}(F)$ | $\frac{1}{K}\sum_t\exp\big(-\|F_t-\tilde F_t\| / \|F_t\|\big)$ | 特征鲁棒性指标 |
| $S_F$ | $w_1\text{Mon}+w_2\text{Trd}+w_3\text{Rob}$ | 特征综合得分 |
| $T_f^{ss}(t)$ | $T_{f0}+\Delta T(e^{\beta t}-1)$ | 稳态摩擦力矩（Stribeck + 指数退化） |
| $\text{MMD}^2(P,Q)$ | $\|\mu_P-\mu_Q\|_\mathcal{H}^2$ | 源-目标域分布差异 |
| $\text{CORAL}(P,Q)$ | $\frac{1}{4d^2}\|C_P-C_Q\|_F^2$ | 二阶矩对齐距离 |
| $\Delta=\widehat{\text{RUL}}-\text{RUL}^{\text{true}}$ | 预测误差 | PHM Score Function 输入 |

---

## 5. 核心假设

1. **准稳态近似**：寿命预测关注累积磨损，复杂转速历史可等效为额定工况 $\omega_0=3000$ rpm 下的平均运行；力矩平衡方程的惯性项 $J\,\dot\omega$ 可忽略，从而 $i(t)\approx T_f^{ss}(\omega_0,t)/K_T$。
   *依据*：题面 §问题2、Zhang et al. (2023) [文献 8]。
   *适用范围*：不适用于点火、消旋等瞬态过程。

2. **Stribeck 三区与退化主因**：稳态摩擦力矩在润滑膜健康时位于弹流润滑区，退化主要由润滑剂挥发/分解导致润滑膜变薄、进入边界润滑所致；退化效应可被电流的长期上升趋势捕捉（"指纹"）。
   *依据*：题面 §问题1；温诗铸《摩擦学原理》[文献 7]。

3. **指数型退化**：稳态摩擦力矩满足 $T_f^{ss}(t)=T_{f0}+\Delta T(e^{\beta t}-1)$；相应地电流退化模型为 $i(t)=i_0+\alpha(e^{\beta t}-1)$，其中 $i_0=T_{f0}/K_T$、$\alpha=\Delta T/K_T$。
   *依据*：题面给定。
   *适用范围*：全寿命的健康-退化-衰退三阶段均适用，但 $\beta$ 在三阶段可能不严格恒定（我们用单一 $\beta$ 拟合平均退化率）。

4. **温度二阶效应可忽略**：附件1 温度变化 35→47 ℃ 区间（12 K）远小于轴承润滑剂工作温度量级（>100 K），且温度变化与摩擦力矩同相，温度对模型不引入独立信息。
   *依据*：附件1 实测温度跨度；Arrhenius 模型对 $\Delta T=12$ K 的修正系数 < 1.5。
   *论文限制说明*：报告中需明确"温度变化大于 20 K 时本假设需重审"。

5. **轴承-飞轮机理同源（迁移学习基础）**：滚动轴承外圈失效与反作用轮轴承外圈失效在物理上同源（润滑剂损耗 → 边界润滑 → 摩擦/振动单调增大）；二者可观测量（轴承振动 RMS、飞轮残差电流）作为同一潜在退化过程的不同投影。
   *依据*：题面 §问题3、§XJTU-SY 介绍。
   *适用范围*：仅对外圈失效轴承成立；内圈/保持架失效仅作为辅助验证，不参与迁移。

---

## 6. 符号约定

- **下标约定**：$t$=时间，$b$=设备/轴承，$k$=特征，$c$=工况；$S$=源域 (Source, 轴承)，$T$=目标域 (Target, 飞轮)。
- **上标约定**：$\hat{(\cdot)}$=估计量；$\tilde{(\cdot)}$=平滑/趋势分量；$(\cdot)^{\text{ss}}$=稳态量；$(\cdot)^{\text{theo}}$=理论值（数据列中已给）。
- **粗体**：向量与矩阵用粗体（如 $\boldsymbol\theta$、$\mathbf{F}$）；标量不加粗。
- **概率约定**：$P(\cdot)$=概率；$\mathbb E[\cdot]$=期望；$B(t)$=标准布朗运动；$\mathcal N(\mu,\sigma^2)$=正态；$\text{IG}(a,b)$=逆高斯（首达时分布）。
- **中英文术语对照**：见 `assets/notes/术语表.md`（待整理）。
