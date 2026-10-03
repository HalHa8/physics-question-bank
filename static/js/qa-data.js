/* MathBank community QA adapted for PhysicsBank. See docs/community-qa.md. */
window.PhysicsBankQaData = {
    "period": {
        "start": "2026-09-08",
        "end": "2026-10-03"
    },
    "entries": [
        {
            "id": "download-release",
            "category": "安装与更新",
            "question": "第一次使用 PhysicsBank，应该从哪里下载？",
            "answer": [
                "Windows 10/11 的 64 位电脑可以下载 Windows 便携包，内含 Python 和运行组件。进入 HalHa8/physics-question-bank 的 GitHub 页面，打开 Actions，选择 main 分支最近一次成功的 CI，在 Artifacts 中下载 PhysicsBank-Windows-x64。具体步骤见 README。",
                "下载可能需要登录 GitHub，构建附件会过期。Code → Download ZIP 下载的是源码，不是便携包；源码用户需按 README 安装依赖。不要沿用 MathBank 的发行版下载链接。"
            ],
            "keywords": [
                "安装",
                "下载",
                "Windows",
                "macOS",
                "便携包",
                "Actions",
                "Artifacts",
                "Release"
            ],
            "sources": [
                {
                    "date": "2026-09-13",
                    "answerSeqs": [
                        1328
                    ]
                }
            ],
            "currentNote": "物理版的下载入口以本仓库 README 为准；当前便携包通过 Actions 构建附件提供，不保证存在 GitHub Release 或 macOS 发布包。"
        },
        {
            "id": "upgrade-with-backup",
            "category": "安装与更新",
            "question": "覆盖更新前要做什么？怎样避免丢失题库？",
            "answer": [
                "先保存尚未入库的编辑，创建并检查完整备份，再用网页电源按钮正常关闭服务。将新版解压到临时目录，把其中的内容复制到原程序目录，替换同名程序文件；macOS Finder 不要整体替换旧文件夹。",
                "保留 math_question_bank.db 及其 WAL/SHM、static/uploads/、data_backup/、.env、.system_generated/ 和 venv/。便携包用户按包内“覆盖升级说明.txt”操作；自己改过代码的用户另外保存修改，Git 源码用户不要强行覆盖未提交改动。"
            ],
            "keywords": [
                "升级",
                "更新",
                "Mac",
                "替换",
                "备份"
            ],
            "sources": [
                {
                    "date": "2026-09-14",
                    "answerSeqs": [
                        1362
                    ]
                },
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        2023,
                        2071
                    ]
                }
            ],
            "currentNote": "以上采用物理版当前覆盖升级契约，纠正历史答复中容易被误解为“整体替换文件夹”的操作。"
        },
        {
            "id": "move-folder",
            "category": "安装与更新",
            "question": "移动程序文件夹后打不开，应该先检查什么？",
            "answer": [
                "群内有一次案例是原服务没有正常关闭。群主建议先把文件夹放回原位置，打开程序后用电源按钮彻底关闭，再移动整个文件夹。",
                "以后移动或复制程序前先停止服务。若仍然打不开，要结合启动日志排查，不能把所有启动失败都归因于这个原因。"
            ],
            "keywords": [
                "启动",
                "打不开",
                "移动",
                "桌面",
                "下载目录"
            ],
            "sources": [
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        2026
                    ]
                }
            ]
        },
        {
            "id": "api-base-url",
            "category": "API 与模型",
            "question": "Base URL 应该填什么？一定要加 /v1 吗？",
            "answer": [
                "填写服务商提供的 API 接口地址，不是服务商网页首页。群主在具体案例中提示补上 /v1；是否需要这段路径，应以所用服务商的接口说明为准，不要对所有地址重复添加。"
            ],
            "keywords": [
                "api",
                "base url",
                "中转站",
                "v1",
                "接口"
            ],
            "sources": [
                {
                    "date": "2026-09-08",
                    "answerSeqs": [
                        1260,
                        1261,
                        1262
                    ]
                },
                {
                    "date": "2026-09-14",
                    "answerSeqs": [
                        1336
                    ]
                }
            ]
        },
        {
            "id": "provider-match",
            "category": "API 与模型",
            "question": "填了 API Key，为什么识图仍提示没有配置，或题干没有自动填入？",
            "answer": [
                "检查“公式识图”等任务实际选择的服务商和模型，再确认该服务商对应的 API Key 已保存。只配置另一家服务商的 Key，不会自动给当前任务使用。正常识别后，结果应进入题干编辑区。",
                "如果配置匹配仍失败，再检查服务商返回的错误和 Key 是否有效；不要仅凭“已经填了 Key”排除接口配置问题。"
            ],
            "keywords": [
                "api",
                "key",
                "识图",
                "配置",
                "服务商",
                "鉴权"
            ],
            "sources": [
                {
                    "date": "2026-09-16",
                    "answerSeqs": [
                        1373,
                        1378,
                        1379
                    ]
                },
                {
                    "date": "2026-09-20",
                    "answerSeqs": [
                        1445,
                        1462
                    ]
                }
            ]
        },
        {
            "id": "vision-model",
            "category": "API 与模型",
            "question": "扫描版 PDF 和截图应该选什么模型？",
            "answer": [
                "图像识别需要支持视觉输入的多模态模型。模型能力应按所用服务商和具体型号核对，不能仅按品牌名判断支持或不支持图片。群聊中的模型推荐属于当时的使用经验，不是长期兼容或效果保证。"
            ],
            "currentNote": "公式识图与试卷拆分是可分别配置的任务。扫描页识别使用识图配置，拆题和属性匹配使用拆卷配置；不要把两个阶段的模型要求混为一谈。",
            "keywords": [
                "扫描",
                "pdf",
                "OCR",
                "视觉",
                "多模态",
                "DeepSeek"
            ],
            "sources": [
                {
                    "date": "2026-09-20",
                    "answerSeqs": [
                        1416,
                        1426,
                        1427,
                        1428,
                        1462
                    ]
                }
            ]
        },
        {
            "id": "custom-api",
            "category": "API 与模型",
            "question": "能接入火山引擎、豆包或其他自定义 API 吗？",
            "answer": [
                "群主说明“中转站”入口相当于自定义配置，可以按服务商的接口地址、模型标识和 Key 尝试接入。",
                "当时并没有确认火山引擎或豆包的兼容性；存在配置入口不等于所有服务商都已测试支持。"
            ],
            "keywords": [
                "api",
                "自定义",
                "火山",
                "豆包",
                "中转站"
            ],
            "sources": [
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        2008,
                        2009,
                        2010
                    ]
                }
            ]
        },
        {
            "id": "large-pdf",
            "category": "导入与识别",
            "question": "能一次导入几百页 PDF 吗？为什么大文件更容易失败？",
            "answer": [
                "不建议一次处理几百页。群主提醒，大文件可能超出模型上下文或输出 token 限制，并建议分成十页以内的小批次，页数越少通常越稳妥。",
                "“十页以内”是使用建议，不是程序强制上限；复杂图文、题量和模型能力同样会影响结果。"
            ],
            "keywords": [
                "pdf",
                "页数",
                "批量",
                "token",
                "上下文",
                "大文件"
            ],
            "sources": [
                {
                    "date": "2026-09-08",
                    "answerSeqs": [
                        1265,
                        1266,
                        1267
                    ]
                }
            ]
        },
        {
            "id": "import-failure",
            "category": "导入与识别",
            "question": "Word / PDF 拆题失败或停在校验阶段，怎样排查？",
            "answer": [
                "先看日志中失败的阶段、页码和具体提示。检查该任务所选服务商、模型和密钥，再缩小导入页码范围。复杂排版、多图或大量题目可能增加处理难度。",
                "公式锁等校验也可能因模型输出不符合约定而失败，不能一律归为模型能力弱，也不要直接关闭校验。保留原文件和脱敏日志反馈；不要因一次失败重新导入全部已成功的题目。"
            ],
            "keywords": [
                "拆卷",
                "失败",
                "卡住",
                "校验",
                "DeepSeek",
                "公式锁"
            ],
            "sources": [
                {
                    "date": "2026-09-20",
                    "answerSeqs": [
                        1423,
                        1513,
                        1541,
                        1542
                    ]
                },
                {
                    "date": "2026-09-23",
                    "answerSeqs": [
                        1667,
                        1673,
                        1683,
                        1695
                    ]
                }
            ],
            "currentNote": "物理版会区分识图/拆卷配置缺失与识图超时或断流。超时请求可能已经计费，系统不会自动付费重试；检查服务状态和费用后，再由您决定手动重试。"
        },
        {
            "id": "custom-tex-import",
            "category": "导入与识别",
            "question": "自定义 LaTeX 模板的试卷拆分失败，有什么替代方式？",
            "answer": [
                "群主处理过因自定义模板导致 TeX 导入困难的案例：可以先把 TeX 编译成 PDF，再尝试导入 PDF。个别题仍需核对和手动调整，不能保证所有自定义模板都能直接拆分。"
            ],
            "keywords": [
                "tex",
                "latex",
                "自定义模板",
                "拆分",
                "pdf"
            ],
            "sources": [
                {
                    "date": "2026-09-17",
                    "answerSeqs": [
                        1395
                    ]
                }
            ]
        },
        {
            "id": "existing-answers",
            "category": "导入与识别",
            "question": "Word 原卷已有答案，能避免 AI 重新生成解答吗？",
            "answer": [
                "不要勾选“AI 生成解答”，系统会尝试匹配原 Word 中已有的答案。群主提醒，答案集中放在卷末时可能匹配不准，仍需逐题核对。",
                "群主当时认为 Word 的答案匹配效果相对较好，PDF 可能较弱；这不是对任何文件都能正确匹配的保证。"
            ],
            "keywords": [
                "word",
                "答案",
                "解析",
                "重复生成",
                "token"
            ],
            "sources": [
                {
                    "date": "2026-09-23",
                    "answerSeqs": [
                        1717,
                        1719,
                        1720,
                        1721,
                        1724
                    ]
                }
            ]
        },
        {
            "id": "pdf-images",
            "category": "导入与识别",
            "question": "PDF 导入能自动提取插图和选项中的图片吗？",
            "answer": [
                "可以尝试自动提取。早期“PDF 插图只能手动补”的回答已经过时：群主在 9 月 25 日宣布开始支持插图提取，9 月 28 日进一步说明新版支持自动截图；10 月 2 日确认 PDF Inspector 可以处理选项中的图片。",
                "这些答复不代表所有复杂排版都能完整恢复。导入后仍要逐题检查缺图、错图和图片位置，必要时手动补图。"
            ],
            "currentNote": "“智能图文提取”支持自动提取与归位；“文字优先”和“全页识图”仍需手动配图。物理题尤其要核对实验装置、电路连接、图像坐标及选项配图，不能仅凭题干文字完整就认定成功。",
            "keywords": [
                "pdf",
                "插图",
                "自动截图",
                "选项图片",
                "PDF Inspector",
                "缺图"
            ],
            "sources": [
                {
                    "date": "2026-09-25",
                    "answerSeqs": [
                        1893
                    ]
                },
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        2053
                    ]
                },
                {
                    "date": "2026-10-02",
                    "answerSeqs": [
                        2755
                    ]
                }
            ]
        },
        {
            "id": "formula-review-warning",
            "category": "导入与识别",
            "question": "出现“公式结构待核对”，是否说明公式一定错了？",
            "answer": [
                "这表示转换结果有不完整或不确定的地方，不代表整道题的每个公式都错了，也不是可以直接隐藏的提示。请对照原文，检查对应公式是否完整，再修正并核对预览。",
                "持续出现时提供脱敏后的原 Word/PDF、出错题号和日志。不同文件可能有不同原因；不要批量删除标记后把题目当作完整结果使用。"
            ],
            "keywords": [
                "公式结构待核对",
                "警告",
                "拆图",
                "导入"
            ],
            "sources": [
                {
                    "date": "2026-09-29",
                    "answerSeqs": [
                        2245,
                        2252,
                        2254,
                        2256
                    ]
                }
            ],
            "currentNote": "Word 公式转换器可能把未能完整转换的结构写为“[公式结构待核对]”，拆题流程会保留标记。物理题还需核对单位大小写、上下标、矢量、正负号和有效数字。"
        },
        {
            "id": "screenshot-latex",
            "category": "编辑与排版",
            "question": "能把题目截图转成可编辑的 LaTeX 吗？",
            "answer": [
                "可以。群主说明截图识别得到的就是 LaTeX 内容，需要先配置识图模型及对应 API。识别完成后在题干编辑区检查和修改，再保存入库；识别结果不保证完全准确。"
            ],
            "keywords": [
                "截图",
                "latex",
                "OCR",
                "题干",
                "识别"
            ],
            "sources": [
                {
                    "date": "2026-09-16",
                    "answerSeqs": [
                        1373
                    ]
                },
                {
                    "date": "2026-09-20",
                    "answerSeqs": [
                        1433
                    ]
                }
            ],
            "currentNote": "物理版仍须对照截图检查单位、物理量上下标、方向、极性、有效数字和插图，不由 AI 猜补不清楚的内容。"
        },
        {
            "id": "image-reference",
            "category": "编辑与排版",
            "question": "怎样把题末的图片移到正文中？删除后又出现怎么办？",
            "answer": [
                "在题干编辑框中找到对应的 Markdown 图片引用，例如 ![](图片路径)。剪切并粘贴到目标文字位置，可改变插入位置。这里调整的是正文引用，不是任意拖动或文字环绕；修改后检查预览并保存。",
                "如果删除正文引用后图片又出现，可能还存在关联配图或绘图引用，不能只删除预览中的图片元素。先核对该题的关联图片与正文；不要直接删除磁盘文件，避免影响其他引用同一图片的题目。"
            ],
            "keywords": [
                "插图",
                "删除",
                "移动",
                "Markdown",
                "位置"
            ],
            "sources": [
                {
                    "date": "2026-09-10",
                    "answerSeqs": [
                        1269
                    ]
                },
                {
                    "date": "2026-09-23",
                    "answerSeqs": [
                        1630,
                        1631
                    ]
                }
            ],
            "currentNote": "导入题卡与普通编辑器的配图状态不同；此问答不把“删除 Markdown 引用”宣称为能够同时清除所有关联图片。"
        },
        {
            "id": "image-border",
            "category": "编辑与排版",
            "question": "预览中的图片外框会出现在导出文件里吗？",
            "answer": [
                "群主说明，网页中的外框用于标识图片和提供交互，正常导出的是图片本身，不会附带这层界面外框。",
                "如果原始图片自身就带边框，导出不会自动去除原图里的边框。"
            ],
            "keywords": [
                "图片",
                "外框",
                "边框",
                "预览",
                "导出"
            ],
            "sources": [
                {
                    "date": "2026-09-20",
                    "answerSeqs": [
                        1489
                    ]
                },
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        2084
                    ]
                }
            ]
        },
        {
            "id": "image-size-wrap",
            "category": "编辑与排版",
            "question": "图片大小能自由调整吗？需要文字环绕怎么办？",
            "answer": [
                "群主说明，系统提供几个固定图片大小档位；任意放大可能影响 PDF 编译和版面。需要更精细的尺寸或文字环绕时，可以导出 Word 后调整。",
                "9 月 23 日的答复中，文字环绕尚未计划实现；不要把 Word 的后期编辑能力当作网页内置功能。"
            ],
            "currentNote": "图片布局菜单已有自动 / 小 / 中 / 大尺寸；题末图片组可选题干右侧及下方居左、居中、居右。这些预设布局不同于任意自由环绕。",
            "keywords": [
                "图片",
                "大小",
                "缩放",
                "大中小",
                "文字环绕",
                "word"
            ],
            "sources": [
                {
                    "date": "2026-09-20",
                    "answerSeqs": [
                        1503
                    ]
                },
                {
                    "date": "2026-09-23",
                    "answerSeqs": [
                        1640,
                        1641
                    ]
                },
                {
                    "date": "2026-10-02",
                    "answerSeqs": [
                        2755
                    ]
                }
            ]
        },
        {
            "id": "math-delimiters",
            "category": "编辑与排版",
            "question": "向量、上下标或公式显示成代码，应该检查什么？",
            "answer": [
                "先检查公式是否放在完整的数学定界符内，例如 $v_0$、$t^2$。矢量可按原题使用 $\\vec{F}$ 或 $\\boldsymbol{F}$；缺少完整的 $...$ 可能影响渲染。",
                "不要把所有 \\mathbf 都改成 \\boldsymbol，也不要把物理单位当成变量改写：单位大小写、正体/斜体及原题指定的矢量字形应保留。"
            ],
            "currentNote": "已有公式、跨行环境和表格会受到保护，自动补定界符仅处理高置信度片段，不能替代人工核对。",
            "keywords": [
                "公式",
                "美元符号",
                "向量",
                "下标",
                "上标",
                "mathbf",
                "boldsymbol",
                "乱码"
            ],
            "sources": [
                {
                    "date": "2026-09-13",
                    "answerSeqs": [
                        1310
                    ]
                }
            ]
        },
        {
            "id": "fraction-size",
            "category": "编辑与排版",
            "question": "分数太小，可以全局把 \\frac 替换成 \\dfrac 吗？",
            "answer": [
                "不宜全局替换。群主建议主体分数使用 \\dfrac，指数、下标里的小分数保留 \\frac，以免破坏层次和行距。"
            ],
            "currentNote": "题干和答案编辑区已有“规范分式”操作。它保护明确的数学结构，只修改当前编辑内容，正常保存后才入库，不会批量修改所有历史题。",
            "keywords": [
                "分数",
                "分式",
                "frac",
                "dfrac",
                "规范分式"
            ],
            "sources": [
                {
                    "date": "2026-09-22",
                    "answerSeqs": [
                        1606
                    ]
                }
            ]
        },
        {
            "id": "choice-environment",
            "category": "编辑与排版",
            "question": "选择题选项应该怎样录入？需要手动加空格排列吗？",
            "answer": [
                "使用项目的 choices 环境，每个选项以 \\item 开头，例如：\\begin{choices} \\item $v=1\\,\\mathrm{m/s}$ \\item $v=2\\,\\mathrm{m/s}$ \\item $v=3\\,\\mathrm{m/s}$ \\item $v=4\\,\\mathrm{m/s}$ \\end{choices}。",
                "让模板自动安排选项布局，不用 \\quad 等空格手动拼成一行。choices 是本项目模板的约定，不是所有 LaTeX 文档都默认提供。单选和多选需要由您确认。"
            ],
            "keywords": [
                "选择题",
                "选项",
                "choices",
                "item",
                "quad"
            ],
            "sources": [
                {
                    "date": "2026-09-26",
                    "answerSeqs": [
                        1920,
                        1922
                    ]
                }
            ]
        },
        {
            "id": "preview-punctuation",
            "category": "编辑与排版",
            "question": "小问前的句号消失，需要输入两个句号吗？",
            "answer": [
                "不需要用重复标点补偿。物理版已合入 MathBank 2.4.1 中小问换段吞掉前一句句号、分号、感叹号等标点的修复。",
                "修复只影响网页预览，不修改已保存原文和 PDF / Word 导出。如果原文已经手动输入两个句号，需要自行核对重复标点。"
            ],
            "keywords": [
                "句号",
                "标点",
                "两个点",
                "换行",
                "小问",
                "2.4.1"
            ],
            "sources": [
                {
                    "date": "2026-09-29",
                    "answerSeqs": [
                        2236
                    ]
                }
            ],
            "currentNote": "2.4.1 是上游修复的版本号，不是 PhysicsBank 的版本号；物理版请通过本仓库更新。"
        },
        {
            "id": "preview-choice-wrap",
            "category": "编辑与排版",
            "question": "选项公式在运算符处意外断行，怎样处理？",
            "answer": [
                "物理版已合入 MathBank 2.4.1 的网页选项布局修复：避免公式在运算符处意外断行，空间不足时自动减少选项列数。",
                "这不等于强制四个选项永远挤在一行。修复只改变网页预览，不改写题目原文和 PDF / Word 导出。"
            ],
            "keywords": [
                "选择题",
                "断行",
                "换行",
                "公式",
                "列数",
                "2.4.1"
            ],
            "sources": [
                {
                    "date": "2026-09-29",
                    "answerSeqs": [
                        2236
                    ]
                }
            ],
            "currentNote": "2.4.1 指上游修复来源；更新 PhysicsBank 请使用本仓库，而不是下载数学版替换。"
        },
        {
            "id": "preview-vs-export",
            "category": "组卷与导出",
            "question": "预览里的分页或空行异常，是否代表导出的 PDF 也一样？",
            "answer": [
                "不一定。群主说明网页预览是模拟排版，不是真正的 LaTeX 编译。可检查导出的 TeX 是否包含相应题目，并实际打开编译得到的 PDF 核对。",
                "不能反过来保证所有缺题都只是预览问题。反馈时同时说明网页表现与实际导出结果，更容易定位。"
            ],
            "keywords": [
                "分页",
                "缺题",
                "空行",
                "预览",
                "pdf",
                "tex"
            ],
            "sources": [
                {
                    "date": "2026-09-13",
                    "answerSeqs": [
                        1321,
                        1322
                    ]
                },
                {
                    "date": "2026-09-24",
                    "answerSeqs": [
                        1736,
                        1737,
                        1743
                    ]
                }
            ]
        },
        {
            "id": "latex-required",
            "category": "组卷与导出",
            "question": "TikZ 绘图和生成 PDF 为什么需要安装 LaTeX？",
            "answer": [
                "TikZ 图形和试卷 PDF 都需要通过 LaTeX 编译。群主建议，有绘图或 PDF 导出需求时安装所需环境。",
                "少量录题且不使用 TikZ 时，可以把原图截图粘贴到题干；这能避免为图片重绘调用编译，但不能替代生成试卷 PDF 所需的环境。"
            ],
            "keywords": [
                "latex",
                "XeLaTeX",
                "TikZ",
                "环境",
                "安装",
                "pdf"
            ],
            "sources": [
                {
                    "date": "2026-09-11",
                    "answerSeqs": [
                        1290
                    ]
                }
            ],
            "currentNote": "基本录题、查题和网页公式预览使用本地 KaTeX，不需要安装 LaTeX。电脑上编译 PDF 或 TikZ 才需要 XeLaTeX；Windows 便携包不等于内置了完整 TeX 环境。"
        },
        {
            "id": "latex-package",
            "category": "组卷与导出",
            "question": "怎样取得 LaTeX 源码？没有安装 LaTeX 也能打包吗？",
            "answer": [
                "使用组卷页面的 LaTeX 打包导出。群主说明，未安装 LaTeX 时也可取得源码包；只有安装环境并编译成功后，才能同时得到生成的 PDF。"
            ],
            "keywords": [
                "latex",
                "源码",
                "tex",
                "打包",
                "zip",
                "导出"
            ],
            "sources": [
                {
                    "date": "2026-09-20",
                    "answerSeqs": [
                        1437,
                        1438,
                        1439
                    ]
                }
            ]
        },
        {
            "id": "pdf-compile-failure",
            "category": "组卷与导出",
            "question": "安装了 LaTeX，为什么仍然无法生成 PDF？",
            "answer": [
                "安装环境不代表任何题干和模板都能成功编译。群主建议先打包导出 TeX 源码，结合编译错误检查题干、模板及相关图片。",
                "反馈时提供可复现的源码或原题与错误日志；不要仅凭“装了 LaTeX”就断定是软件问题，也不要把所有失败都归为同一种语法错误。"
            ],
            "keywords": [
                "pdf",
                "编译",
                "失败",
                "latex",
                "tex",
                "日志"
            ],
            "sources": [
                {
                    "date": "2026-09-13",
                    "answerSeqs": [
                        1312,
                        1317,
                        1322
                    ]
                },
                {
                    "date": "2026-09-17",
                    "answerSeqs": [
                        1389,
                        1391
                    ]
                }
            ]
        },
        {
            "id": "paper-title",
            "category": "组卷与导出",
            "question": "试卷标题和模板可以修改吗？",
            "answer": [
                "在组卷中选择“常规试卷”等适用模板，修改试卷信息中的标题。物理版默认使用常规试卷，修改标题不会自动切换教材目录。",
                "接入任意外部 LaTeX 模板需要另行适配，不是改标题即可完成。"
            ],
            "keywords": [
                "标题",
                "初中",
                "高中",
                "模板",
                "试卷信息"
            ],
            "sources": [
                {
                    "date": "2026-09-23",
                    "answerSeqs": [
                        1707
                    ]
                }
            ],
            "currentNote": "PhysicsBank 默认课程是人教版高中物理 2019（P），不是数学 A/B/S/H 大纲。"
        },
        {
            "id": "custom-question-type",
            "category": "组卷与导出",
            "question": "自定义题型在旧版本导出时不显示，怎么办？",
            "answer": [
                "常规试卷和日常小练支持按题型配置导出；遇到题型没有显示时，先核对所用模板、题型设置以及实际导出文件。",
                "更新后仍缺题时，附题型配置和脱敏导出样例反馈，不要把早期数学版的限制当成物理版当前规则。"
            ],
            "keywords": [
                "自定义题型",
                "导出",
                "常规试卷",
                "日常小练",
                "缺题"
            ],
            "sources": [
                {
                    "date": "2026-09-11",
                    "answerSeqs": [
                        1292,
                        1293,
                        1294
                    ]
                },
                {
                    "date": "2026-09-12",
                    "answerSeqs": [
                        1296
                    ]
                }
            ],
            "currentNote": "物理版默认题型为单选、多选、填空、实验、计算和简答；实验与简答按书面作答题排版。"
        },
        {
            "id": "generate-answer-later",
            "category": "编辑与排版",
            "question": "导入时没有解析，之后还能让 AI 补充吗？",
            "answer": [
                "可以。群主给出的操作是先把题目导入题库，再打开题目使用 AI 解析功能。生成后仍需人工核对，确认后保存。"
            ],
            "currentNote": "题目编辑器有 AI 智能生成解答入口，导入题卡也提供 AI 生成解析操作；无需重新导入整份试卷。",
            "keywords": [
                "ai",
                "解析",
                "答案",
                "补充",
                "解答"
            ],
            "sources": [
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        2058,
                        2059
                    ]
                }
            ]
        },
        {
            "id": "local-backup",
            "category": "数据与备份",
            "question": "题库数据存在哪里？升级前应该备份什么？",
            "answer": [
                "题目保存在程序目录中的本地 SQLite 数据库 math_question_bank.db，插图在 static/uploads/，自定义元数据和备份在 data_backup/。覆盖升级前先保存浏览器中尚未入库的编辑，再创建并检查完整备份。",
                "当前可用 python -m scripts.backup 创建带校验的完整备份，包含数据库、数据库引用的插图和自定义元数据，不包含 .env、API Key、本地控制令牌或浏览器草稿。私密 API 配置如需迁移，请另行安全保存，不能公开发送。"
            ],
            "currentNote": "data_backup/questions_backup.json 只是同步导出，不等同于完整恢复备份。完整备份也可能含私人题目，不适合作为公开题包。",
            "keywords": [
                "备份",
                "数据库",
                "sqlite",
                "db",
                "data_backup",
                "uploads",
                "env"
            ],
            "sources": [
                {
                    "date": "2026-09-24",
                    "answerSeqs": [
                        1749
                    ]
                },
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        2071
                    ]
                }
            ]
        },
        {
            "id": "migrate-computer",
            "category": "数据与备份",
            "question": "换电脑时可以迁移原题库吗？",
            "answer": [
                "可以。群主在新电脑已具备所需运行及导出环境的前提下，说明可复制完整本地题库文件夹迁移。请先停止旧服务并保留备份，再迁移题库和图片。",
                "不要只复制数据库而漏掉插图与自定义配置；跨系统时还需要使用适合新系统的程序和依赖，不能直接复用另一系统的运行环境。"
            ],
            "currentNote": "先保存入库并保留完整备份；恢复前停止服务，按 scripts.restore 的检查与恢复流程操作。跨系统须重新准备适用的程序和依赖。PhysicsBank 与 MathBank 应保持独立目录与数据库，不自动混用数学题库。",
            "keywords": [
                "迁移",
                "换电脑",
                "数据目录",
                "恢复",
                "Mac",
                "Windows"
            ],
            "sources": [
                {
                    "date": "2026-09-14",
                    "answerSeqs": [
                        1344
                    ]
                },
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        2071
                    ]
                }
            ]
        },
        {
            "id": "ai-readable-library",
            "category": "数据与备份",
            "question": "能把题库给 AI 检索，或迁移到其他题库系统吗？",
            "answer": [
                "群主说明，题目保存在 SQLite 中，也曾提供 data_backup 下的 Markdown 题库文件供 AI 读取。题量大时不宜把整份文件一次塞进模型，可按需检索。",
                "迁移到其他系统仍需转换字段和格式；这不意味着与其他题库一键兼容。"
            ],
            "currentNote": "data_backup/questions_library.md 仍是自动生成的 AI 只读题库，包含题干、插图和大纲，不包含答案解析。它不是完整备份，不应直接改写来替代题库保存；项目另有 scripts/search_questions.py 按需检索工具。",
            "keywords": [
                "ai",
                "检索",
                "markdown",
                "questions_library",
                "sqlite",
                "迁移"
            ],
            "sources": [
                {
                    "date": "2026-09-24",
                    "answerSeqs": [
                        1749,
                        1883,
                        1884,
                        1885
                    ]
                }
            ]
        },
        {
            "id": "share-without-secrets",
            "category": "数据与备份",
            "question": "分享修改后的项目或整包时，怎样避免泄露 API Key？",
            "answer": [
                "群主提醒，API Key 配置在 .env 中，打包前要排除敏感配置，不能直接分享自己的完整工作目录或私密备份。",
                "同时检查配置副本、日志和截图，确认没有密钥、令牌或无关个人信息。只删除公开文件不代表已撤销泄露的凭据；如果已经泄露，应到相应服务商撤销并更换。"
            ],
            "keywords": [
                "api key",
                "隐私",
                "密钥",
                "泄露",
                "env",
                "分享",
                "打包"
            ],
            "sources": [
                {
                    "date": "2026-10-01",
                    "answerSeqs": [
                        2367,
                        2443
                    ]
                }
            ]
        },
        {
            "id": "custom-curriculum",
            "category": "定制与反馈",
            "question": "学段、章节和目录可以修改吗？",
            "answer": [
                "可以在系统设置中调整自定义元数据、章节和目录。先整理需要的目录并做好备份，再修改相关配置；不要通过批量改题干文字代替目录设置。"
            ],
            "keywords": [
                "学段",
                "章节",
                "大纲",
                "目录",
                "设置",
                "自定义维度"
            ],
            "sources": [
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        1982,
                        1984
                    ]
                }
            ],
            "currentNote": "物理版默认人教版高中物理 2019（P）。设置中的目录定制不等于已内置所有学段、教材或任意学科一键切换。"
        },
        {
            "id": "report-issue",
            "category": "定制与反馈",
            "question": "怎样反馈故障？应该提供哪些信息？",
            "answer": [
                "在 HalHa8/physics-question-bank 的 GitHub Issues 反馈，尽量提供版本、系统、导入方式、失败阶段与页码、复现步骤和完整报错。原文件只在确认有权分享且已检查隐私后提供。",
                "启动日志通常在 .system_generated/server.log；该目录可能隐藏。公开发送前先去除 API Key、本地控制令牌、个人路径、学生信息和不便公开的题目内容。不要发送整个工程或 .env。"
            ],
            "keywords": [
                "issue",
                "反馈",
                "bug",
                "日志",
                "server.log",
                "报错"
            ],
            "sources": [
                {
                    "date": "2026-09-21",
                    "answerSeqs": [
                        1560,
                        1561
                    ]
                },
                {
                    "date": "2026-09-23",
                    "answerSeqs": [
                        1667
                    ]
                },
                {
                    "date": "2026-09-28",
                    "answerSeqs": [
                        2063,
                        2064
                    ]
                }
            ],
            "currentNote": "物理版的问题请反馈到物理版仓库；需要转交上游的通用问题，再由维护者核对。"
        }
    ],
    "origin": {
        "project": "MathBank",
        "commit": "705b852454de08717940d49e7272c31b9b54a778",
        "adaptedFor": "PhysicsBank",
        "verifiedOn": "2026-10-03"
    }
};
