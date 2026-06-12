# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules

1. **Communication**: 每次沟通都以"老大"开头。
2. **TDD-first**: 任何代码变更前先写/更新测试，确保所有测试通过后才进行代码修改。

## Run

```bash
pip install -r requirements.txt
python3 app.py
```

Default: `http://localhost:5000`. Config path defaults to `config.json`, overridable via `CONFIG_PATH` env var. Port overridable via `PORT` env var.

## Project Documentation

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for API endpoints, PDF processing pipeline, frontend architecture, and configuration.
