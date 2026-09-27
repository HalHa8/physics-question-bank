# PhysicsBank: Local High-School Physics Question Bank

[简体中文](README.md) · [AGPL-3.0 license](LICENSE) · [Notices](NOTICE.md)

PhysicsBank is a local-first question bank, AI-assisted solution, import, search,
and paper-layout workbench for high-school physics. It is based on
[JudgePeach/math-question-bank](https://github.com/JudgePeach/math-question-bank)
and includes upstream functionality through MathBank 2.4.0 and its subsequent
main-branch commit, including PDF extraction and source-image review, Word
import review, and school-level symbol support. Physics-specific source review
checks units, vector directions, circuit connections, and experimental apparatus.

The physics adaptation adds a 2019 PEP high-school physics curriculum, six
physics-oriented question types, physics-specific OCR and solution prompts,
and regular-exam defaults. Data and API keys remain local by default.

> This project does not bundle a freely redistributable question collection.
> Imported questions, papers, and images remain subject to their own copyright
> and usage terms.

For each new PhysicsBank work session, first check the upstream MathBank `main`
branch and review any changes before integrating them. This is an interactive
project workflow, not an unattended background updater or an automatic GitHub push.

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

XeLaTeX is required for PDF compilation and TikZ previews, but not for question
entry, import, search, or LaTeX source export. Pandoc is recommended for editable
Word formulas. Neither tool is installed silently. For development, install
`requirements-dev.txt`, then run `python -m pip check` and `python -m pytest -q`.

Never commit `.env`, API keys, local databases, personal backups, uploaded
question images, or student data. See the [Chinese README](README.md) for the
full feature and dependency matrix.

## License

PhysicsBank is distributed under GNU AGPL-3.0. It preserves the original
project history and notices; see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
If a modified version is offered to users over a network, provide those users
with the Corresponding Source for the version that is actually running. This
license does not automatically relicense imported questions or private data.
