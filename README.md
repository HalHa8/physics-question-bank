# PhysicsBank：本地高中物理题库与组卷工作台

[English](README_EN.md) · [AGPL-3.0 许可证](LICENSE) · [修改说明](NOTICE.md)

PhysicsBank 基于 [JudgePeach/MathBank](https://github.com/JudgePeach/math-question-bank) 改造，面向高中物理教师和学习者。它在本机管理题目、导入试卷、辅助解析和组卷；网页界面无需前端编译，题库默认存于本地 SQLite 数据库。

> 本项目是物理适配版，不附带可自由转载的试题库。导入的试卷、题目和图片仍受其各自的版权或使用许可约束。

## 主要功能

| 场景 | 能力 |
| --- | --- |
| 题库管理 | 录入、检索和分类图文混排题目；网页实时预览公式、图片和解析 |
| 试卷导入 | 图片 OCR，以及 PDF、Word、LaTeX 试卷的拆题与来源核对；不确定内容保留人工复核 |
| AI 辅助 | 按需配置模型进行解题、知识点分类、智能选题和物理示意图辅助重绘 |
| 组卷导出 | 常规试卷的题型顺序与版式配置；导出 Word、LaTeX 源码包，以及在装有 XeLaTeX 时编译 PDF |

## 物理版优化

- 内置人教版普通高中物理 2019 课程树，覆盖三册必修和三册选择性必修。
- 默认题型调整为单选题、多选题、填空题、实验题、计算题和简答题。
- OCR 强调物理量、矢量方向、单位、有效数字、实验表格及图像坐标。
- AI 解答遵循“研究对象—物理过程—正方向—规律—方程—单位—合理性检查”。
- 试卷导出默认使用物理学科名称，组卷默认采用可配置的常规试卷，而不是数学 19 题模板。
- TikZ 提示词面向受力图、电路图、光路图、运动图像和场线图。
- 已合入上游 2.4.0 及其后续提交的 PDF 提取、原卷图文核对、Word 导入复核和中学符号支持；原文核对增加物理量、单位、方向、极性、电路连接、实验装置等检查，物理课程与题型仍为默认配置。

数学 A/B/S/H 课程预设和原 `exam_19` 模板仅保留旧数据兼容，不作为物理版默认入口。

## 安装与启动

需要 Python 3.10 或更新版本。推荐先创建独立 Conda 环境，避免与 MathBank 共用依赖或数据库：

```powershell
git clone https://github.com/HalHa8/physics-question-bank.git
cd physics-question-bank
conda create -n physicsbank-py310 python=3.10 -y
conda activate physicsbank-py310
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

然后打开 <http://127.0.0.1:8001/>。基础录题、检索和网页公式预览不需要 AI 密钥、LaTeX 或 Node.js。开发和运行测试时再安装 `requirements-dev.txt`。

Windows 也可双击 `启动题库系统.bat`，它会准备项目内的 `venv` 并打开浏览器；**该启动器目前固定使用 8000 端口**。若同一台电脑上的 MathBank 已占用 8000，请按上面的命令在 8001 启动物理版，或先正常关闭占用端口的服务。不要让两个项目指向同一个目录或数据库。

### 可选的 AI 配置

需要 OCR、AI 解答或智能选题时，可在应用的 API 设置中配置服务商和模型，也可参考 `.env.example` 创建本机 `.env`。不要把真实密钥写入示例文件或提交到 Git。调用外部 AI 服务时，相应题目内容或图片会发送给所选服务商；含学生隐私或无传播许可的材料请先核对使用条件。

### 可选的排版工具

LaTeX 是系统级软件，不会随 Python 依赖安装：

| 功能 | XeLaTeX | Pandoc |
|---|---:|---:|
| 题目录入、检索、分类与网页公式预览 | 不需要 | 不需要 |
| 图片 OCR、试卷导入 | 不需要 | 不需要 |
| 导出 LaTeX 源码包 | 不需要 | 不需要 |
| 编译 PDF 试卷和 TikZ 物理示意图 | **需要** | 不需要 |
| 导出含可编辑公式的 Word 文档 | 仅降级路径需要 | **建议安装** |

Windows 上如需完整 PDF 与 TikZ 功能，推荐安装完整 TeX Live，也可以使用 MiKTeX。安装后重新打开终端并确认：

```powershell
where.exe xelatex
xelatex --version
```

本项目不会静默安装 TeX 发行版。具体导出效果取决于本机工具链、字体及源题内容，尤其应人工核对电路连接、箭头方向、图像刻度和公式。

## 数据与隐私

首次启动会在**本项目目录**创建独立数据库和本地配置。下列个人数据已被 Git 忽略，公开仓库不应包含它们：

- `.env` 与 API 密钥
- `*.db` 题库数据库
- `data_backup/` 中的个人备份与导出
- `static/uploads/` 中的题目图片

升级前建议自行备份数据库与上传图片；不要把 MathBank 的数据目录直接覆盖到 PhysicsBank。软件的 AGPL 许可证适用于程序代码，不会让你导入的题目、讲义、学生数据或密钥自动变成 AGPL 内容。

## 验证与开发

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m pip check
```

服务启动后可访问 `/healthz` 查看就绪状态，访问 `/api/version` 查看当前物理版版本。每次继续开发 PhysicsBank 时，先检查 MathBank 上游 `main`，审查新提交并安全适配物理默认值；这是一项会话内工作约定，不是后台自动更新，也不意味着自动推送或发布。

## 来源、修改与许可证

本项目基于 [JudgePeach/math-question-bank](https://github.com/JudgePeach/math-question-bank) 修改，保留原项目历史与版权声明，并依据 [GNU Affero General Public License v3.0](LICENSE) 发布。

本修改版源代码主页：<https://github.com/HalHa8/physics-question-bank>

主要修改包括高中物理课程树、物理题型、物理 AI 提示词、原卷校验、界面文案和试卷导出默认值，详见 [NOTICE.md](NOTICE.md)。若向他人提供本修改版的网络服务，须按 AGPL 要求提供**与实际运行版本对应**的完整源代码。

题目及图片的再使用权需要另行向其来源确认。
