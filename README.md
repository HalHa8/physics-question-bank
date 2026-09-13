# PhysicsBank：本地高中物理题库与组卷工作台

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

PhysicsBank 是一个面向高中物理教师和学习者的本地题库、试题导入、AI 辅助解析与组卷排版工具。数据默认保存在自己的电脑中，支持图片 OCR、PDF/Word/LaTeX 试卷拆题、知识点分类、题目检索、Word/PDF 导出和物理示意图辅助重绘。

> 当前版本为早期物理适配版。AI 功能需要自行配置兼容 OpenAI API 格式的文本或多模态模型；PDF 编译和 TikZ 绘图需要本机安装 XeLaTeX。

## 物理版优化

- 内置人教版普通高中物理 2019 课程树，覆盖三册必修和三册选择性必修。
- 默认题型调整为单选题、多选题、填空题、实验题、计算题和简答题。
- OCR 强调物理量、矢量方向、单位、有效数字、实验表格及图像坐标。
- AI 解答遵循“研究对象—物理过程—正方向—规律—方程—单位—合理性检查”。
- 试卷导出默认使用物理学科名称，组卷默认采用可配置的常规试卷，而不是数学 19 题模板。
- TikZ 提示词面向受力图、电路图、光路图、运动图像和场线图。

## 快速开始

推荐 Python 3.10 或更高版本，并使用独立虚拟环境：

```bash
conda create -n physicsbank-py310 python=3.10 -y
conda activate physicsbank-py310
python -m pip install -r requirements-dev.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

浏览器访问 `http://127.0.0.1:8001`。Windows 用户也可以双击 `启动题库系统.bat`，但请确保它使用的是独立的物理版目录。

首次启动会在项目目录创建独立数据库及本地配置。以下内容已被 Git 忽略，不应上传到 GitHub：

- `.env` 与 API 密钥
- `*.db` 数据库
- `data_backup/` 中的个人题库导出和备份
- `static/uploads/` 中的题目图片

## 可选的排版软件

LaTeX 不是 Python 包，因此不会随 `pip install -r requirements-dev.txt` 安装。PhysicsBank 把它设计成可选的系统级工具：

| 功能 | XeLaTeX | Pandoc |
|---|---:|---:|
| 题目录入、检索、分类与网页公式预览 | 不需要 | 不需要 |
| 图片 OCR、PDF/Word/LaTeX 试卷导入 | 不需要 | 不需要 |
| 导出 LaTeX 源码包 | 不需要 | 不需要 |
| 编译 PDF 试卷和 TikZ 物理示意图 | **需要** | 不需要 |
| 导出含可编辑公式的 Word 文档 | 仅降级路径需要 | **建议安装** |

Windows 上如需完整 PDF 与 TikZ 功能，推荐安装完整 TeX Live，也可以使用 MiKTeX。安装后重新打开终端并确认：

```powershell
where.exe xelatex
xelatex --version
```

本项目不会静默安装 TeX 发行版，因为它体积较大、属于系统级软件，并涉及安装位置、镜像源和自动补包策略等用户选择。启动诊断会显示 `latex=missing` 或检测到的实际路径。

## 当前限制

- 原项目的 `exam_19` 数学模板仍作为兼容代码保留，但物理版界面不再将它作为默认模板；建议使用“常规试卷”并自定义题型顺序。
- 课程树目前提供人教版 2019 物理大纲，其他教材版本可在设置中通过 JSON 自定义。
- 电路图等复杂图形仍依赖 AI 输出和本地 LaTeX 环境，导出前应人工核对方向、连接与数值。

## 测试

```bash
python -m pytest -q
python -m pip check
```

## 来源、修改与许可证

本项目基于 [JudgePeach/math-question-bank](https://github.com/JudgePeach/math-question-bank) 修改。原项目及本修改版均依据 [GNU Affero General Public License v3.0](LICENSE) 发布。

本修改版源代码主页：<https://github.com/HalHa8/physics-question-bank>

主要修改包括高中物理课程树、物理题型、物理 AI 提示词、界面文案和试卷导出默认值，详见 [NOTICE.md](NOTICE.md)。如果把修改后的程序部署为供他人访问的网络服务，应按 AGPL-3.0 第 13 条在界面中明显提供与运行版本对应的完整源代码。

题目、讲义、学生数据和 API 密钥不因使用本程序而自动采用 AGPL；这些内容仍受其各自来源、版权和隐私规则约束。
