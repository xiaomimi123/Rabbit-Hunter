# 猎兔者 V6 · Field Instrument · Design System V2

> **状态**:V2 草案,旗舰页 `Dashboard` 已经做出预览(`./dashboard-preview.html`,浏览器打开即可看)
>
> **替换对象**:V1 cyan/violet 全息卡 + cyber-grid(被 frontend-design skill 鉴定为 AI 默认风格之一)
>
> **设计方向锚点**:产品中文名"猎兔者" + 操作员真实工作姿态(长时间凝视 + 决断瞬间)→ **田野精密仪器** (Field Instrument)
>
> 该方向参照:瞄准镜 / 测距仪 / 罗盘 / 田野日志 / 旧黄铜钟表面

---

## 0. 设计原则(取舍清单)

| 我们追求 | 我们拒绝 |
|---|---|
| 黄铜 / 苔藓绿 / 干涸血红 | 霓虹 cyan / 紫色渐变 |
| Instrument Serif + Fira Code | Inter / JetBrains Mono(AI 默认对) |
| 边栏批注 (marginalia) | 模态框堆叠 |
| 同心圆瞄准镜 (Aperture) 标志 | 全息边框 / glow effect |
| 0.5px 发丝线分层 | 圆角卡片 / drop shadow |
| 慢速旋转的 aperture(6s)| 闪烁脉动 (neon-pulse) |
| 对角线纸纹底 | 32px 方格 cyber-grid |
| 暖象牙白文字 #F1ECDD | 纯白 #FFFFFF |
| 不对称 KPI 比例 2:1:1:1 | 均分四等卡片 |

---

## 1. 色板(CSS variables)

```css
:root {
  /* surfaces */
  --bg-base:        #0F1115;   /* 暖近黑(不死黑) */
  --bg-surface:     #171A20;
  --bg-elevated:    #22272F;
  --bg-deep:        #0A0C0F;
  --hairline:       rgba(241, 236, 221, 0.10);
  --hairline-strong:rgba(241, 236, 221, 0.18);

  /* text */
  --text-ivory:     #F1ECDD;   /* 旧象牙,非纯白 */
  --text-sec:       rgba(241, 236, 221, 0.72);
  --text-mut:       rgba(241, 236, 221, 0.42);
  --text-dim:       rgba(241, 236, 221, 0.26);

  /* semantic accents — 保留 LONG=绿/SHORT=红 惯例,但泥土化 */
  --sage:           #6B8568;   /* LONG / WIN / healthy(苔藓绿,非亮绿) */
  --sage-soft:      rgba(107, 133, 104, 0.18);
  --oxblood:        #A53E32;   /* SHORT / LOSS(干涸血红,非警报红) */
  --oxblood-soft:   rgba(165, 62, 50, 0.18);

  /* signature accent — 真正非常规 */
  --brass:          #C9A14B;   /* 高亮 / 当前活动 / 品牌字符 */
  --brass-soft:     rgba(201, 161, 75, 0.14);

  /* support */
  --ink:            #5A7691;   /* 信息(古地图墨蓝) */
  --ink-soft:       rgba(90, 118, 145, 0.18);
  --ash:            #7B8590;   /* 中性数据 */
  --alarm:          #D03B30;   /* 仅留给 LIVE 模式切换确认 */
}
```

**色板的"非 AI 默认性"自检**:

- ✗ 无 `#22D3EE` 类霓虹 cyan
- ✗ 无 `#A78BFA` 类柔紫
- ✗ 无紫色渐变
- ✗ 无 acid green / vermilion
- ✓ Brass `#C9A14B`(钟表黄铜)— **几乎不出现在 AI 配色板里**
- ✓ Oxblood `#A53E32`(干涸血)— 比 `#EF4444` 更"古"
- ✓ Sage `#6B8568`(苔藓)— 比 `#10B981` 更"自然"

---

## 2. 字体配对

```css
--font-display: 'Instrument Serif', 'Source Han Serif SC', serif;  /* 标题/品牌 */
--font-body:    'Source Serif 4', 'Noto Serif SC', serif;          /* 正文/批注 */
--font-mono:    'Fira Code', ui-monospace, monospace;              /* 数据/数字 */
--font-cn:      'Noto Serif SC', serif;                            /* 中文导航 */
```

**选择理由**:
- **Instrument Serif**(Google Fonts 免费)— 字面就叫 "Instrument"(仪器),意大利体笔画戏剧化,非常规
- **Source Serif 4** — Adobe 开源,可变,有 8pt~60pt opsz,正文批注密度大也能读
- **Fira Code** — 等宽连字,**不是 JetBrains Mono**(AI 默认)
- 中英对位:衬线 + 衬线统一调性

**字号系统**:

```
显示英文 hero       2.6rem  Instrument Serif
显示英文 KPI 大数    4.0rem  Instrument Serif(数字 ss01)
显示英文 section    1.4rem  Instrument Serif
数据数字 KPI        3.1rem  Fira Code, tabular-nums
数据数字 stat       1.5rem  Fira Code
正文中文            0.875rem Noto Serif SC
正文批注            0.78rem  Source Serif 4 italic
标签等宽            0.66rem  Fira Code, letter-spacing 0.22em UPPERCASE
```

---

## 3. 标志性元素 — The Aperture

**形态**:同心圆 + 十字标线 (concentric circles + crosshair),像瞄准镜/显微镜/手表表盘

**SVG 源(可缩放)**:
```svg
<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="0.7">
  <circle cx="20" cy="20" r="18" />
  <circle cx="20" cy="20" r="12" />
  <circle cx="20" cy="20" r="6" />
  <line x1="20" y1="0" x2="20" y2="6" stroke-width="1.2" />
  <line x1="20" y1="34" x2="20" y2="40" stroke-width="1.2" />
  <line x1="0" y1="20" x2="6" y2="20" stroke-width="1.2" />
  <line x1="34" y1="20" x2="40" y2="20" stroke-width="1.2" />
</svg>
```

**七种用法**:
1. **品牌标识**(sidebar 顶部,28px,brass 色)
2. **页面标题前**(34px,慢速旋转 6s linear infinite)
3. **section 标题前**(18px,固定不动)
4. **空状态占位**(80px,带 sweep 动画)
5. **loading**(慢速旋转 + 透明度脉动)
6. **数据焦点**(被 hover 的 KPI 卡角落显示小 aperture)
7. **导航 active 项的 glyph**(`⊕` Unicode 字符备选)

**视觉语义**:Aperture 出现 = "正在瞄准/正在观测/正在确认"。它替代了 V1 里的 cyan 全息边框作为"系统在工作"的视觉信号。

---

## 4. 布局原则

### 4.1 不对称 KPI 比例

```
┌─────────────────┬─────────┬─────────┬─────────┐
│  Hero KPI       │  KPI 2  │  KPI 3  │  KPI 4  │
│  (1.7 fr)       │ (1 fr)  │ (1 fr)  │ (1 fr)  │
│                 │         │         │         │
│  Big number     │ Number  │ Number  │ Number  │
│  in Display     │  mono   │  mono   │  mono   │
└─────────────────┴─────────┴─────────┴─────────┘
```

最重要的指标(Dashboard 上是"胜率",Active Positions 上是"当前 PnL")用 1.7fr 拉大、用 Display Serif 而非 mono 字体 — 视觉等级清晰,操作员的眼睛 0.2 秒锁定。

### 4.2 边栏批注 (Marginalia)

每个 section 是 `grid-template-columns: 1fr 200px` — 右边 200px 是批注区,放:
- 数据的人话解读("78% washed at conjunction. RSI ∩ MACD remains the dominant filter")
- 异常注解("Auto strategy underperforms manual by 34pt")
- 上下文链接("funding extreme setups now passing at higher rate")

**字体处理**:`Source Serif 4 italic 0.78rem text-mut`,左边 `1px solid hairline` 分隔。重点词用 brass 色高亮(无下划线、无加粗)。

### 4.3 发丝线分层

不用色块、不用阴影、不用 border-radius。**所有层级靠 0.5px hairline**:
- `--hairline 10% ivory` — 默认分隔(数据行之间)
- `--hairline-strong 18% ivory` — 重要分隔(section 之间、page-head 下方)

### 4.4 网格背景

V1 的 `cyber-grid` 32px 方格替换为**对角线纸纹**:
```css
body {
  background-image:
    repeating-linear-gradient(
      45deg,
      rgba(241,236,221,0.012) 0,
      rgba(241,236,221,0.012) 1px,
      transparent 1px,
      transparent 6px
    );
}
```

视觉上几乎看不见,但屏幕"质感"从塑料变成纸。

---

## 5. 动效

### 5.1 用 / 不用

| 动效 | 用 | 不用 |
|---|---|---|
| Aperture 旋转 6s linear | ✓ 页面标题 | ✗ 不要给所有 aperture 加 |
| 数字翻转 50ms slot-machine | ✓ PnL/胜率变化时 | ✗ 不要给所有数字加 |
| Hover 发丝线染 brass | ✓ 数据行 hover | ✗ 不要变色块 |
| Sweep loading | ✓ 占位/loading 状态 | ✗ 不要默认 spinner |
| **`neon-pulse` 脉动** | ✗ 永久弃用 | |
| **闪烁渐变** | ✗ 永久弃用 | |

### 5.2 总原则

- 每个页面**只允许 1 处常驻动效**(通常是 page-head 的 aperture)
- 数据变化时的动画是"反应",不是"装饰"
- 减速曲线统一 `cubic-bezier(0.4, 0, 0.2, 1)`

---

## 6. 数字处理(神圣不可变)

```css
.num, .mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}
```

- **所有数字** tabular-nums + Fira Code
- **价格**:`0.16649`(完整保留,不缩写)
- **百分比**:`63%` `+5.2%` `−1.9%`(用真正的 minus `−` U+2212,不是连字符)
- **PnL**:`+18.40 USDT`(色染整段,sage / oxblood)
- **z-score**:`z=+2.4` `z=−2.6`(`★` 标记 |z|≥2 的)
- **right-align** 所有数据列

---

## 7. 旗舰页面参考实现

详见 `./dashboard-preview.html`(独立 HTML,无 build,浏览器双击即可看)

实现了:
- ✓ AppShell:sidebar + topbar + content,完整骨架
- ✓ Page Header:Aperture 旋转 + 显示衬线 hero "Dashboard"
- ✓ KPI Row:1.7:1:1:1 不对称布局,Hero 用 Display Serif
- ✓ Signal Funnel:4 级漏斗,每级不同 accent 色(ink → ink-soft → brass-soft → sage-soft)
- ✓ Win Rate Breakdown:左右双栏,左边按 side/strategy/exit 分组横条,右边聚合统计
- ✓ PnL Trajectory:SVG 折线,sage 色,end-point brass dot
- ✓ Setup Type 表格:funding_extreme_* 行 brass 底,有 `✦` 前缀
- ✓ Block Reason 分布:细 bar(4px 高),oxblood 色
- ✓ 每个 section 都有右侧 marginalia 解读

**如何复现到 React**:每个 CSS 类对应一个 React component / Tailwind utility。下一步可以走 subagent-driven 把它接入实际 `V5DashboardPage.tsx`。

---

## 8. 给其他 AI 生成器的简洁 prompt

如果你想让 v0 / Lovable / Bolt 按这个方向继续生成其他页面,可以把这段贴给它们:

```
Design direction: "Field Instrument" — like a precision hunting/observation tool,
NOT cyber/neon.

Palette: warm near-black (#0F1115) base, aged ivory (#F1ECDD) text, accents are
sage moss green (#6B8568) for LONG/WIN, oxblood (#A53E32) for SHORT/LOSS, and
brass (#C9A14B) for highlights. NEVER use neon cyan, violet gradients, or any
generic "tech" color.

Fonts: Instrument Serif (display, italic for accents), Source Serif 4 (body),
Fira Code (data/numbers). NEVER use Inter, JetBrains Mono, or Space Grotesk.

Signature element: a concentric-circle crosshair (rifle-scope aperture) used as
section markers and brand glyph. SVG provided below.

Layout rules: asymmetric KPI grid (1.7:1:1:1), marginalia column on the right of
every section (italic body serif, brass-color highlights), 0.5px hairline rules
for ALL separation (no borders, no shadows, no rounded corners > 4px).

Motion: ONE rotating aperture on page-head (6s linear). NO neon-pulse, no glow,
no shimmer. Numbers can do a 50ms slot-machine flip when they change.

[Then attach the dashboard-preview.html as visual reference]
```

---

## 9. 接下来

| 下一步 | 工作量 | 价值 |
|---|---|---|
| 浏览器预览 dashboard-preview.html | 0 分钟 | 看是否认可方向 |
| 出第二张参考页(`V5ActivePositionsPage`) | 1 turn | 验证方向能否承载交易关键页 |
| 出第三张参考页(`V5AIStatusPage`) | 1 turn | 验证方向能否承载"AI 风格"页 |
| 抽出 Tailwind config + CSS variables 文件 | 1 turn | 给 React 接入做地基 |
| Subagent-driven 重写 `V5DashboardPage.tsx` | 多 turn | 实际接入 |
| 全部 12 页 + 14 组件迁移 | ~20 task | 完整落地 |

建议顺序:看完 dashboard 预览 → 决定方向是否锁定 → 再决定接入节奏(整体重写 / 逐页 / A-B 共存)。
