# PhysicsBank: Local High-School Physics Question Bank

PhysicsBank is a local-first question bank, AI-assisted solution, import, search,
and paper-layout workbench for high-school physics.

This is an early physics adaptation of
[JudgePeach/math-question-bank](https://github.com/JudgePeach/math-question-bank).
It adds a 2019 PEP high-school physics curriculum, physics-oriented question
types and AI prompts, and physics paper defaults.

## Run from source

```bash
conda create -n physicsbank-py310 python=3.10 -y
conda activate physicsbank-py310
python -m pip install -r requirements-dev.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001`.

Never commit `.env`, API keys, local databases, personal backups, uploaded
question images, or student data.

## License

PhysicsBank is distributed under GNU AGPL-3.0. It preserves the original
project history and notices; see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
If a modified version is offered to users over a network, provide those users
with the Corresponding Source for the version that is actually running.
