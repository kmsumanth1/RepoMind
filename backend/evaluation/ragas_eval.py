"""Answer-quality evaluation with RAGAS (faithfulness = hallucination check, answer relevancy).

    pip install ragas datasets
    export ANTHROPIC_API_KEY=...            # generation LLM used by RepoMind
    python -m evaluation.ragas_eval --repo-dir data/indexed_repos/tiangolo__fastapi

NOTE: RAGAS needs its own *judge* LLM + embeddings, configured per the RAGAS docs for your version
(by default it looks for an OpenAI key). RAGAS' API changes between releases, so this script is a thin,
UNTESTED adapter: it builds {question, answer, contexts} rows from RepoMind's real pipeline; adjust the
`evaluate(...)` call/metrics imports to the RAGAS version you install.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.config import get_config
from generation.llm_client import get_llm

from .retrieval_metrics import load_engine


def build_rows(engine, questions: list[dict]) -> list[dict]:
    rows = []
    for q in questions:
        if not q["relevant"]:
            continue                                   # only answerable questions have something to be faithful to
        ans = engine.answer(q["question"])
        hits = engine.retrieve(engine.condense(q["question"], []), "full")
        rows.append({"question": q["question"], "answer": ans.answer, "contexts": [h.chunk.text for h in hits]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-dir", required=True)
    ap.add_argument("--dataset", default=str(Path(__file__).with_name("eval_dataset.json")))
    args = ap.parse_args()
    cfg = get_config()
    engine = load_engine(Path(args.repo_dir), cfg)
    engine.llm = get_llm(cfg)                          # real generator, not the extractive stand-in
    rows = build_rows(engine, json.loads(Path(args.dataset).read_text())["questions"])

    from datasets import Dataset                       # noqa: E402
    from ragas import evaluate                         # noqa: E402
    from ragas.metrics import answer_relevancy, faithfulness  # noqa: E402

    result = evaluate(Dataset.from_list(rows), metrics=[faithfulness, answer_relevancy])
    print(result)


if __name__ == "__main__":
    main()
