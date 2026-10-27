<p align="center">
  <img src="docs/images/physicsbank-avatar-b.png" alt="PhysicsBank 头像：书页与摆锤" width="112">
</p>

# PhysicsBank：面向高中物理老师的本地题库与组卷工具

**[⬇ Windows 便携包][windows-download] · [📦 源码 ZIP][source-zip] · [🏷 Release 发行页][releases]**

[物理版特色](#physics) · [下载与启动](#download) · [AI 与排版配置](#setup) · [升级与备份](#upgrade) · [交流反馈](#community) · [English](README_EN.md)

PhysicsBank 基于 [MathBank][upstream] 改造，面向高中物理的日常备课、题目积累和试卷编排。保留原项目的本地题库、公式预览、试卷导入和 A4 组卷能力，重点适配物理教材、实验题、多幅配图与物理量表达。

题库默认保存在自己的电脑上。基本录题、检索和组卷不需要 AI；使用识图、解题等功能时，再配置自己的模型服务。**本项目不附带可自由转载的试题库。**

> [!TIP]
> **第一次使用？** 推荐下载 [Windows 正式便携包][windows-download]，完整解压后双击启动，无需另装 Python。先手动录入一道题熟悉操作，再按需配置 AI。

---

<a id="physics"></a>

## 🧲 物理版特色：相对于 MathBank 改了什么？

| 物理备课需要 | PhysicsBank 的适配 |
| --- | --- |
| 按物理教材存题 | 内置人教版高中物理 2019 教材目录，覆盖必修与选择性必修六册，按书册、章节和小节整理。 |
| 区分物理题型 | 默认提供单选、多选、填空、实验、计算和简答六种题型，组卷使用普通物理试卷模板。 |
| 查找跨章节综合题 | 内置 80 个物理知识点，支持主要／辅助考查、别名和个人知识点。例如组合筛选“动量守恒定律＋动能定理”。 |
| 保留单位、方向和图形条件 | 识图、拆题和解答提示词强调单位大小写、量纲、矢量、正负号、有效数字、坐标轴及电路连接；实验题兼顾操作、数据处理和误差分析。结果仍需教师核对。 |
| 多图题也能紧凑组卷 | 保留原图，在题库预览和试卷中分别调整图片百分比；组卷默认较小，空间合适时四个图片选项同排，缩放滑条不占打印版面。 |
| 修正识图时的插图 | 默认从原截图裁取配图，保留正文、选项、表格中的位置；可手动补图、重新截图，不必把每幅图另存再上传。 |

题库管理还增加了章节目录、分类筛选和首页统计。“待归类”用于检查教材、章节、题型或难度缺失；“待细分到小节”用于整理只定位到章节的题目。详情中的“重新分类建议”先显示原分类与建议，**确认应用并保存后才写入**，取消不会改动题目。

教材位置、考查知识点和个人标签分别管理；旧题不会因为升级就自动重新分类。上述通用交互也可能与上游后续功能重合，具体采用范围见[适配说明](docs/mathbank-3-physics-adaptation.md)和[上游同步记录](docs/upstream-sync.md)。

## ✨ 继续保留的核心能力

- **收题与整理**：手动录题、截图录题，导入 PDF、Word、LaTeX 和 Markdown，按题型、来源、难度或知识点查找。
- **预览与组卷**：公式和插图实时预览，A4 模拟排版、拖拽排序、答题留白，导出 Word、LaTeX 源码和 PDF。
- **按需使用 AI**：辅助识图、拆题、解答、分类与选题；不同任务可配置各自的服务商和模型。
- **保存与分享**：草稿、完整备份和题目分享包；离线 QA 页面可搜索安装、导入和排版等常见问题。

共用能力源于 MathBank 及后续适配。原项目的完整介绍见 [MathBank README][upstream-readme]；本项目不代表已同步上游所有最新功能。

<a id="download"></a>

## 🚀 下载与快速开始

| 下载方式 | 适合谁 | 当前状态 |
| --- | --- | --- |
| **[⬇ Windows 正式便携包][windows-download]** | 希望解压后直接使用的老师 | **v0.1.0** · Windows 10/11 64 位 · 内含 Python 与运行依赖。 |
| **[📦 对应版本源码 ZIP][source-zip]** | 已有 Python 环境或希望自行修改的用户 | v0.1.0 完整源码；需自行安装依赖，不是便携包。 |
| **[🏷 Release 发行页][releases]** | 查看版本说明、附件与历史版本 | 正式发布渠道；附件不受 CI 构建产物的保留期限限制。 |

### 🖥️ 方式一：Windows 便携包（推荐）

1. **下载正式包**

   点击 [PhysicsBank-Windows-x64.zip][windows-download]，公开附件无需登录 GitHub。

2. **完整解压**

   解压到独立文件夹，不要在压缩软件内直接运行，也不要覆盖 MathBank 的目录。

3. **双击启动**

   运行 **`启动题库系统.bat`**；浏览器通常会自动打开，也可访问 <http://127.0.0.1:8000/>。

> [!NOTE]
> 正式包不设使用到期时间。需要检查下载完整性时，可下载 [SHA-256 校验文件][windows-sha256]。AI、PDF 编译和 Word 导出仍有各自的[配置要求](#setup)。

MathBank 与 PhysicsBank 请放在不同文件夹，分别保存题库。若 MathBank 已占用 8000 端口，请先在其网页中正常关闭服务；源码用户也可按下面的示例用 8001 端口运行。

<details>
<summary>🛠️ 方式二：源码 ZIP 或 Git 启动（展开查看）</summary>

先[下载源码 ZIP][source-zip]并完整解压，或使用 Git：

```powershell
git clone https://github.com/HalHa8/physics-question-bank.git
cd physics-question-bank
git switch --detach v0.1.0
```

如果下载的是 ZIP，请先进入解压后的项目目录。需要 Python 3.10 或更新版本；下面用 Conda 创建独立环境：

```powershell
conda create -n physicsbank-py310 python=3.10 -y
conda activate physicsbank-py310
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

打开 <http://127.0.0.1:8001/>。已有其他独立 Python 环境的用户可直接使用，不必另外安装 Conda。macOS 暂无本仓库已发布的便携包，可按源码方式运行；源码目录中的 `启动题库系统.command` 要求本机有 Python 3.10+，首次准备环境需要联网。

</details>

<details>
<summary>🔎 最新开发源码与备用 CI 下载（展开查看）</summary>

- [下载 main 最新源码 ZIP][main-zip]：可能包含正式版之后的改动，不保证已有对应便携包。
- [查看 main 构建记录][ci]：选择成功的构建，在 **Artifacts → PhysicsBank-Windows-x64** 下载。此方式需要 GitHub 登录，附件有保留期限。
- CI 下载文件外层还包含便携包 ZIP 和校验文件，须再解压内部 ZIP；正式 Release 的直链则直接下载便携包。

</details>

---

<a id="setup"></a>

## ⚙️ AI 和排版软件怎样配置？

| 想做什么 | 需要准备 |
| --- | --- |
| 手动录题、检索、网页公式预览、组卷 | 不需要 AI 密钥或本地 LaTeX。 |
| 截图识题、PDF／Word 自动拆题 | 在「系统设置」配置相应模型；识图模型必须支持图片输入，多题拆分还需试卷拆解模型。 |
| AI 解答、分类、选题 | 配置对应任务的 API Key 和模型，费用以服务商实际计费为准。 |
| 本机编译 PDF 或 TikZ 图形 | 安装提供 XeLaTeX 的排版环境，如 [TeX Live](https://www.tug.org/texlive/) 或 [MiKTeX](https://miktex.org/)。 |
| 导出含可编辑公式的 Word | 需要 Pandoc，按系统页面提示配置或安装。 |

截图可上传、拖入或粘贴；单题可勾选“自动生成 AI 解答与详细解析”，一图多题请选择“整页／多题拆分”。入库前请核对题干、单位、公式、配图和答案对应关系。

选择文件、手动裁图和打开分类建议入口不会调用模型；点击识别、分析或解答后才发起相应请求。额外原卷核验默认关闭，启用可能增加费用；识图、拆题失败后不会自动重复付费请求。题目使用 AI 时会发送给所配置的服务商。

<a id="upgrade"></a>

## 🔄 升级、备份与分享

1. **先备份**：保存未入库编辑，使用「系统设置」的完整备份，并另行保管自己的 API 配置。
2. **正常关闭再更新**：通过网页关闭题库，将新版解压到临时目录，再按包内 `覆盖升级说明.txt` 替换程序文件。源码用户更新代码后，在原独立环境重新安装 `requirements.txt`。
3. **保留个人数据**：保留数据库及 WAL/SHM、`static/uploads/`、`data_backup/`、`.env`、`.system_generated/` 和 `venv/`。数据库需要升级时会先创建快照；回退旧程序须恢复升级前的完整备份。

> [!IMPORTANT]
> **更新前先备份，分享时只发题包。** 不要把使用过的整个程序目录发给别人，里面可能有自己的题库和 API 配置。

给同事发题时，使用「系统设置 → 题库分享」导出选题 ZIP；接收方在同一页面选择导入，系统校验并自动备份后追加题目。分享包包含题目和引用图片，不含 API 密钥或运行配置。**重复导入会再次新增题目**，不会自动查重合并。完整备份用于恢复，不能代替选题分享流程。

---

<a id="community"></a>

## 💬 使用帮助与交流

- **日常操作**：打开程序中的「QA」，按主题或关键词查找，无需联网或调用 AI。
- **反馈问题**：[提交 Issue][issues]，说明下载日期、操作步骤和报错；附图前请遮住 API 密钥及私人信息。
- **QQ 交流群**：**904544454**。

<p align="center">
  <img src="docs/images/physicsbank-qq-group.png" alt="PhysicsBank QQ 交流群二维码，群号 904544454" width="272">
</p>

## 📄 致谢与开源说明

感谢 [JudgePeach 与 MathBank 贡献者][upstream]。PhysicsBank 保留原项目历史与声明，按 [AGPL-3.0](LICENSE) 开源，修改说明见 [NOTICE.md](NOTICE.md)。软件许可证不等于试题授权；自行导入的题目、试卷和图片仍须遵守各自的使用条件。

[windows-download]: https://github.com/HalHa8/physics-question-bank/releases/download/v0.1.0/PhysicsBank-Windows-x64.zip
[windows-sha256]: https://github.com/HalHa8/physics-question-bank/releases/download/v0.1.0/PhysicsBank-Windows-x64.zip.sha256
[source-zip]: https://github.com/HalHa8/physics-question-bank/archive/refs/tags/v0.1.0.zip
[main-zip]: https://github.com/HalHa8/physics-question-bank/archive/refs/heads/main.zip
[releases]: https://github.com/HalHa8/physics-question-bank/releases
[ci]: https://github.com/HalHa8/physics-question-bank/actions/workflows/ci.yml?query=branch%3Amain
[issues]: https://github.com/HalHa8/physics-question-bank/issues
[upstream]: https://github.com/JudgePeach/math-question-bank
[upstream-readme]: https://github.com/JudgePeach/math-question-bank/blob/main/README.md
