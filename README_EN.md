<p align="center">
  <img src="docs/images/physicsbank-avatar-b.png" alt="PhysicsBank book and pendulum avatar" width="112">
</p>

# PhysicsBank: A local question bank and paper builder for physics teachers

**[⬇ Windows portable package][windows-download] · [📦 Source ZIP][source-zip] · [🏷 Releases][releases]**

[Physics adaptations](#physics) · [Download and start](#download) · [AI and export setup](#setup) · [Upgrade and backup](#upgrade) · [Help](#community) · [简体中文](README.md)

PhysicsBank adapts [MathBank][upstream] for high-school physics preparation.
It keeps the local bank, formula preview, document import and A4 paper builder,
with physics curricula, question types, diagrams and physical-quantity handling.

The bank is stored on your computer. Manual editing, search and paper assembly
work without AI; configure your own provider when you need recognition or solutions.
**The project does not bundle a freely redistributable question collection.**

> [!TIP]
> **New here?** Download the [Windows release][windows-download], extract it fully and double-click the launcher. Python is included. Try manual entry first and configure AI only when needed.

---

<a id="physics"></a>

## 🧲 What changes for physics?

| Teaching need | PhysicsBank adaptation |
| --- | --- |
| Physics textbook placement | The 2019 PEP high-school physics curriculum, covering six compulsory and selective-compulsory books, chapters and sections. |
| Physics question types | Single choice, multiple choice, fill-in, experiment, calculation and short answer, with a regular physics paper default. |
| Cross-topic retrieval | 80 starter physics points, main/auxiliary roles, aliases and teacher-created points. Combine momentum conservation and the work-energy theorem, for example. |
| Faithful physical content | OCR, import and solution prompts emphasize unit case, dimensions, vectors, signs, significant figures, axes and circuit connections. Experiment solutions address procedure, data processing and errors. Teacher review remains necessary. |
| Diagram-heavy papers | Separate percentage scales for bank previews and paper items; smaller paper defaults, four image choices in one row when space permits, and controls outside the printed layout. |
| Correcting extracted figures | Crop from the original screenshot into its text, option or table position; manually add or recrop figures without uploading every diagram separately. |

The bank also provides a chapter directory, classification filters and homepage
statistics. **Unclassified** identifies missing textbook/chapter/type/difficulty;
**Needs a section** identifies valid chapter placement without a current section.
**Reclassification suggestions** show the existing placement and proposed result;
only explicit confirmation applies and saves them.

Textbook placement, physics points and personal tags remain separate. Upgrading
does not automatically relabel existing questions. Some general interface features
may overlap with subsequent upstream changes; see the
[adaptation scope](docs/mathbank-3-physics-adaptation.md) and
[upstream sync record](docs/upstream-sync.md).

## ✨ Core capabilities retained from MathBank

- **Collect and organize:** manual or screenshot entry; PDF, Word, LaTeX and Markdown import; search by type, source, difficulty or knowledge point.
- **Preview and build papers:** formulas and figures, simulated A4 layout, drag sorting, answer space, and Word, LaTeX or PDF export.
- **Optional AI:** recognition, paper splitting, solutions, classification and selection, with task-specific provider settings.
- **Save and share:** drafts, full backups, selected-question ZIPs and searchable offline QA.

These shared capabilities come from MathBank and selected adaptations.
See the [original README][upstream-readme] for the upstream project;
PhysicsBank does not claim to include every latest upstream feature.

<a id="download"></a>

## 🚀 Download and start

| Download | Intended users | Availability |
| --- | --- | --- |
| **[⬇ Windows release][windows-download]** | Teachers who prefer extracting and launching | **v0.1.0** · Windows 10/11 x64 · Python and runtime dependencies included. |
| **[📦 Matching source ZIP][source-zip]** | Users with Python or developers | Complete v0.1.0 source; install dependencies separately. Not the portable package. |
| **[🏷 Releases][releases]** | Release notes, attachments and earlier versions | Official downloads are not subject to CI artifact retention periods. |

### 🖥️ Option 1: Windows portable package (recommended)

1. **Download the official package**

   Get [PhysicsBank-Windows-x64.zip][windows-download]. Public release attachments require no GitHub login.

2. **Extract everything**

   Use a dedicated folder, not your MathBank folder. Do not run from inside an archive viewer.

3. **Double-click the launcher**

   Run **`启动题库系统.bat`**. If a browser does not open, visit <http://127.0.0.1:8000/>.

> [!NOTE]
> The application has no usage expiry. A [SHA-256 checksum][windows-sha256] is available for integrity checks. AI, PDF compilation and Word export have separate [setup requirements](#setup).

Keep MathBank and PhysicsBank in separate folders with separate data. If MathBank
uses port 8000, close it normally through its page, or use port 8001 from source.

<details>
<summary>🛠️ Option 2: Source ZIP or Git (expand)</summary>

[Download the source ZIP][source-zip] and extract it, or clone:

```powershell
git clone https://github.com/HalHa8/physics-question-bank.git
cd physics-question-bank
git switch --detach v0.1.0
```

For a ZIP download, enter the extracted project directory first.
Python 3.10+ is required. An isolated Conda environment is one option:

```powershell
conda create -n physicsbank-py310 python=3.10 -y
conda activate physicsbank-py310
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

Open <http://127.0.0.1:8001/>. Conda is optional if you already have an isolated
Python environment. This repository has no published macOS portable package;
use source. The source `启动题库系统.command` launcher requires an installed
Python 3.10+ and internet access for initial environment preparation.

</details>

<details>
<summary>🔎 Development source and backup CI downloads (expand)</summary>

- [Latest main source ZIP][main-zip] may contain changes newer than the official release and may not have a matching portable build.
- [Main CI runs][ci]: open a successful run and download **Artifacts → PhysicsBank-Windows-x64**. This requires GitHub login and is subject to retention limits.
- A CI download contains an inner portable ZIP and checksum; extract the inner ZIP too. Official release links download the portable ZIP directly.

</details>

---

<a id="setup"></a>

## ⚙️ AI and export setup

| Task | Requirements |
| --- | --- |
| Manual entry, search, formula preview and paper assembly | No AI key or local LaTeX installation. |
| Screenshot recognition or automated PDF/Word splitting | Configure the corresponding tasks; OCR requires an image-capable model, and multi-question splitting also needs a parsing model. |
| AI solutions, classification and selection | Configure the task's API key and model; provider usage may incur fees. |
| Local PDF or TikZ compilation | XeLaTeX, for example through [TeX Live](https://www.tug.org/texlive/) or [MiKTeX](https://miktex.org/). |
| Word export with editable equations | Pandoc; follow the application's setup or installation prompt. |

Upload, drop or paste screenshots. For a single question, optionally enable
automatic detailed solutions; for whole pages, select multiple-question mode.
Review text, units, formulas, figure placement and answers before saving.

Choosing files, manual cropping and opening classification suggestions make no
model calls. Recognition, analysis and solution actions send the relevant content
to your configured provider. Extra source verification is off by default and may
increase costs; failed recognition or splitting does not automatically resend paid requests.

<a id="upgrade"></a>

## 🔄 Upgrade, backup and sharing

1. **Back up first:** save pending edits, create a full backup in Settings and separately retain your API configuration.
2. **Close normally before updating:** stop the service through its page, extract the update into a temporary folder and follow `覆盖升级说明.txt`. Source users should reinstall `requirements.txt` in their existing isolated environment after updating.
3. **Preserve personal data:** databases and WAL/SHM, `static/uploads/`, `data_backup/`, `.env`, `.system_generated/` and `venv/`. Required database migrations create a snapshot first; rollback needs the pre-upgrade full backup.

> [!IMPORTANT]
> **Back up before updating; share question packages only.** Do not send an entire used application folder: it may contain private data and API configuration.

Use **Settings → Library sharing** for a selected-question ZIP. Import there
validates the package and creates a full backup before appending questions.
The package includes questions and referenced images,
not API keys or runtime settings. **Repeated import appends duplicates**; there is
no automatic merge. Full backups serve recovery rather than selected-question sharing.

<a id="community"></a>

## 💬 Help and community

- **Usage help:** search the application's offline QA by topic or keyword.
- **Report problems:** [open an issue][issues] with the package date, steps and error; redact keys and private information.
- **QQ group:** **904544454**.

<p align="center">
  <img src="docs/images/physicsbank-qq-group.png" alt="PhysicsBank QQ group QR code, group 904544454" width="272">
</p>

## 📄 Credits and license

Thanks to [JudgePeach and the MathBank contributors][upstream].
PhysicsBank retains the original history and notices under [AGPL-3.0](LICENSE);
see [NOTICE.md](NOTICE.md). The software license does not grant rights to imported
questions, papers or images; their own usage terms continue to apply.

[windows-download]: https://github.com/HalHa8/physics-question-bank/releases/download/v0.1.0/PhysicsBank-Windows-x64.zip
[windows-sha256]: https://github.com/HalHa8/physics-question-bank/releases/download/v0.1.0/PhysicsBank-Windows-x64.zip.sha256
[source-zip]: https://github.com/HalHa8/physics-question-bank/archive/refs/tags/v0.1.0.zip
[main-zip]: https://github.com/HalHa8/physics-question-bank/archive/refs/heads/main.zip
[releases]: https://github.com/HalHa8/physics-question-bank/releases
[ci]: https://github.com/HalHa8/physics-question-bank/actions/workflows/ci.yml?query=branch%3Amain
[issues]: https://github.com/HalHa8/physics-question-bank/issues
[upstream]: https://github.com/JudgePeach/math-question-bank
[upstream-readme]: https://github.com/JudgePeach/math-question-bank/blob/main/README.md
