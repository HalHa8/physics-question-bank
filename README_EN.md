<p align="center">
  <img src="docs/images/physicsbank-avatar-b.png" alt="PhysicsBank book and pendulum avatar" width="112">
</p>

# PhysicsBank: Local High-School Physics Question Bank

The Import Center now has a **Screenshot / Image** entry: upload, drop or paste
images. Single-question mode opens the existing OCR editor for review and saving.
Its optional automatic-answer checkbox runs the configured solver after OCR;
it is off by default. Existing answers and source answer labels are preserved.
Incomplete questions pause for correction, and late results cannot replace edits.
Whole-page / multiple-question mode accepts up to 20 ordered images (10MB each,
50MB total), with move-up/down and remove controls, then uses the existing paper
splitting and question-review workflow. Choosing/reordering images stays local;
recognition starts only when requested. Multi-question mode needs both image OCR
and paper-parsing models. TeX companion illustrations remain a separate input.
Independent physics points are now separate from textbook placement and personal
tags. The editor supports manual main/auxiliary labels, 80 starter points,
aliases, teacher-created points and draft persistence. Bank filters support
ANY/ALL, main-only and unlabeled questions. Optional AI classification uses the
existing request to suggest points with literal evidence; suggestions remain
pending until a teacher confirms them. Manual editing/search makes no AI calls.
The `main` branch integrates reusable MathBank 3.0 and 3.0.1 improvements while retaining physics
content rules, screenshot corrections and per-paper image scales. PhysicsBank's own schema is v12 (not MathBank's version numbering),
with a database snapshot before migration; existing questions are not relabeled.
Make a full backup and close the service before upgrading. Older programs cannot
open the upgraded database; rollback requires the pre-upgrade full backup and
separate preservation of any newly added data. Portable packages are unchanged.

Screenshot OCR now crops figures directly from the original image, preserving
their text, option or table positions. Original-image mode is enabled by default.
Unresolved or inaccurate figures can be manually cropped or re-cropped from the
same screenshot; a separate illustration upload is unnecessary. Cropping is
local and needs no LaTeX or extra AI review request. Check labels, axes, polarity
and circuit connections before saving. Turning off original-image mode explicitly
enables extra paid TikZ drawing calls per figure.

These changes and all three backend-decoupling stages are integrated into the
`main` source. Existing Windows portable packages are not rebuilt by a local
source update; check the downloaded build's commit and back up personal data.

Settings → Library sharing exports selected questions, answers, labels and
referenced images as a ZIP without credentials or runtime configuration. Import
validates the package, creates a full backup, and appends without overwriting.
Repeated imports append again; they do not automatically merge duplicates.
Sharing now shows task stages and progress. Refreshing or reconnecting queries
the original task without uploading again. If the commit outcome is uncertain,
check your library and backup before importing again. An intentional repeat
requires explicit confirmation. Storage preflight reports permission, space
and file-lock problems without elevating privileges or moving your data.
Check content permissions and personal information before sharing.

Markdown import, source-preserving classification, batch figure crops, tables,
lists, image profiles and missing-asset export preflight are supported. Extra
PDF/Word visual verification remains opt-in and may cost money. Failed paid
requests are not automatically retried or silently routed to another provider.
Word recovery requires an explicit click and may send unfinished requests.
Upstream PDF local-project/fragment/checkpoint experiments remain disabled.

See the [adaptation scope and acceptance record](docs/mathbank-3-physics-adaptation.md) for included features and deliberate differences.

[简体中文](README.md) · [AGPL-3.0 license](LICENSE) · [Notices](NOTICE.md)

PhysicsBank is a local-first question bank, AI-assisted solution, import, search,
and paper-layout workbench for high-school physics. It is based on
[JudgePeach/math-question-bank](https://github.com/JudgePeach/math-question-bank)
and selectively adapts subsequent upstream PDF/Word import upgrades. This is not
a claim that every upstream feature is synchronized; see [sync notes](docs/upstream-sync.md).
Physics-specific source review
checks units, vector directions, circuit connections, and experimental apparatus.

The physics adaptation adds a 2019 PEP high-school physics curriculum, six
physics-oriented question types, physics-specific OCR and solution prompts,
and regular-exam defaults. Data and API keys remain local by default.

Browser previews support explicit upright constants `\iu` / `\upi` and
`\eu` / `\upe` without rewriting ordinary current/charge variables `i` and `e`.
Legacy-library startup repairs preserve custom knowledge labels and independent
physics curriculum records.

> This project does not bundle a freely redistributable question collection.
> Imported questions, papers, and images remain subject to their own copyright
> and usage terms.

For each new PhysicsBank work session, first check the upstream MathBank `main`
branch and review any changes before integrating them. This is an interactive
project workflow, not an unattended background updater or an automatic GitHub push.

## Windows portable package

On Windows 10/11 x64, download the `PhysicsBank-Windows-x64` artifact from the
[latest successful CI run on `main`](https://github.com/HalHa8/physics-question-bank/actions/workflows/ci.yml?query=branch%3Amain).
GitHub may require you to sign in. Unzip the downloaded artifact, then fully
extract the `PhysicsBank-Windows-x64.zip` inside it into a separate folder.
Double-click `启动题库系统.bat` there and open <http://127.0.0.1:8000/> if your
browser does not open automatically. Python and the required runtime are
included. `Code → Download ZIP` is source code, not the portable package.
CI artifacts expire; if none is available, use the source instructions below.
Back up your database before moving or updating the extracted folder; see
`覆盖升级说明.txt` inside the package.

## Run from source

```bash
git clone https://github.com/HalHa8/physics-question-bank.git
cd physics-question-bank
conda create -n physicsbank-py310 python=3.10 -y
conda activate physicsbank-py310
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

Open <http://127.0.0.1:8001/>. The Windows `启动题库系统.bat` launcher prepares a
project-local virtual environment but currently uses port **8000**. Use the
command above on port 8001 if MathBank occupies 8000; keep both projects'
directories and databases separate.

Basic question entry, search, and browser formula preview need no AI key, TeX
installation, or Node.js. Configure a provider in the app's API settings or
create a local `.env` from `.env.example` for AI features. External AI requests
send the selected question content or images to that provider; review privacy
and reuse rights first.
Automatic PDF/Word question splitting needs a configured parsing model. Pages
whose text cannot be extracted reliably also need an image-capable OCR model;
the app will not silently accept incomplete native text as a complete page.

The upgraded importer preserves reliable native content and original answers,
uses bounded local/hybrid recognition for uncertain regions, and retains source
evidence and visible review markers. Shared temporary images are copied on save.
Retired images can be recovered through their original references; the private
retention store has no automatic expiry and is not a substitute for a full backup.
Extra source verification stays off by default; failed model requests are not
automatically retried or switched to another provider. After backing up, reinstall
`requirements.txt` in your environment to obtain the upgraded PDF dependency.

XeLaTeX is required for PDF compilation and TikZ previews, but not for question
entry, import, search, or LaTeX source export. Pandoc is recommended for editable
Word formulas. Neither tool is installed silently. For development, install
`requirements-dev.txt`, then run `python -m pip check` and `python -m pytest -q`.

Never commit `.env`, API keys, local databases, personal backups, uploaded
question images, or student data. See the [Chinese README](README.md) for the
simple Windows setup guide.

## QQ user group

Group number: **904544454**.

<p align="center">
  <img src="docs/images/physicsbank-qq-group.png" alt="PhysicsBank QQ user group QR code" width="272">
</p>

## License

PhysicsBank is distributed under GNU AGPL-3.0. It preserves the original
project history and notices; see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
If a modified version is offered to users over a network, provide those users
with the Corresponding Source for the version that is actually running. This
license does not automatically relicense imported questions or private data.
