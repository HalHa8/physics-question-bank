<p align="center">
  <img src="docs/images/physicsbank-avatar-b.png" alt="PhysicsBank 头像：书页与摆锤" width="112">
</p>

# PhysicsBank：给物理老师用的本地题库

PhysicsBank 是一个运行在自己电脑上的高中物理备课工具。您可以收集题目、按教材章节整理、导入试卷、查看公式和插图，再挑题组成新试卷。题库默认保存在本机，不会因为打开网页就自动上传。

它是在 [MathBank](https://github.com/JudgePeach/math-question-bank) 的基础上改造的物理版本，内置人教版高中物理课程目录，支持单选、多选、填空、实验、计算和简答题。

## 可以用它做什么？

- **存题、找题**：把题干、图片和解析放在一起，按章节和题型查找。
- **整理旧试卷**：导入图片、PDF 或 Word 试卷，辅助识别和拆题；公式、单位、电路图等重要内容请在保存前人工核对。
- **组卷、导出**：选题组成试卷，可导出 Word、LaTeX 源码；电脑装有 XeLaTeX 后还可编译 PDF。
- **按需使用 AI**：配置自己的模型服务后，可辅助识题、解题和选题；不用 AI 也能录题、检索和组卷。

PDF、Word 等试卷的**自动拆题需要配置试卷拆解模型的 API Key**；如果某页文字或公式无法可靠提取，还需要配置支持图片输入的识图模型。系统不会把识别不可靠的页面当作正确原文直接导入。

## Windows 用户：如何开始？

目前本仓库提供源码，**尚无现成的 PhysicsBank 便携包**。第一次使用需要电脑已安装 [Python 3.10 或更新版本](https://www.python.org/downloads/)并能联网安装依赖。

1. 点击本页面上方的 **Code → Download ZIP**，将压缩包完整解压到一个文件夹。
2. 双击文件夹中的 **`启动题库系统.bat`**。首次启动会自动为 PhysicsBank 准备独立的 Python 环境，可能需要等待几分钟。
3. 浏览器打开后即可使用；如果没有自动打开，请访问 <http://127.0.0.1:8000/>。

如果电脑上的 MathBank 已经占用 8000 端口，请先在 MathBank 网页中正常关闭它，再启动 PhysicsBank。两个项目应放在不同文件夹，不要共用数据库。熟悉命令行的用户也可以参阅下面的源码启动方式，改用 8001 端口同时运行。

<details>
<summary>源码启动（已有 Python / Conda 的用户）</summary>

```powershell
git clone https://github.com/HalHa8/physics-question-bank.git
cd physics-question-bank
conda create -n physicsbank-py310 python=3.10 -y
conda activate physicsbank-py310
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

然后访问 <http://127.0.0.1:8001/>。Conda 不是必需的，只是隔离环境的一种方式。

</details>

## AI 和排版软件需要安装吗？

**基本录题、查题和网页公式预览不需要 AI 密钥，也不需要安装 LaTeX。** 想用 AI 识图、解题或选题时，在网页设置中填写您自己的服务商信息。题目或图片会发送给该服务商，请先确认材料的隐私和使用许可。

只有在电脑上直接编译 **PDF 试卷或 TikZ 示意图**时才需要 XeLaTeX（如 TeX Live 或 MiKTeX）；导出可编辑公式的 Word 文件时建议安装 Pandoc。缺少这些软件不影响日常题库使用。

## 数据、题目版权与开源说明

题库数据库、上传图片、备份和 API 密钥留在本机；更新或换电脑前，请自行备份这些数据，勿将其上传到公开仓库。**本项目不附带可自由转载的题库**：自行导入的题目、试卷和图片仍受各自的版权或使用条件约束。

本项目保留了 MathBank 的历史与声明，按 [AGPL-3.0](LICENSE) 开源；物理版修改见 [NOTICE.md](NOTICE.md)。若您修改程序并通过网络提供给其他人使用，需要按 AGPL 要求提供对应版本的源代码。软件许可证不会自动改变您个人题目或学生资料的归属。

## QQ 交流群

欢迎交流使用体验与问题。群号：**904544454**。

<p align="center">
  <img src="docs/images/physicsbank-qq-group.png" alt="PhysicsBank QQ 交流群二维码，群号 904544454" width="272">
</p>

[English](README_EN.md)
