"""Retrieval evaluation with stage-by-stage ablation.

    python -m evaluation.retrieval_metrics --repo-dir data/indexed_repos/tiangolo__fastapi

Modes (each adds one component, so you can quote real before/after numbers):
    dense -> bm25 -> hybrid -> hybrid+rerank -> full (adds graph expansion)

Metrics
    Recall@k   fraction of labelled relevant items found in the top-k chunks (averaged over questions)
    MRR        mean reciprocal rank of the first relevant item found
    CtxRecall  fraction of relevant items present anywhere in the final context handed to the LLM
               (this is where graph expansion shows up: it appends callers/callees after the top-k)
    Guard      answerable questions wrongly refused (lower is better) / unanswerable questions refused (higher is better)
A relevant item is {"file": ..., "symbol": optional}; a chunk matches if the file matches and, when given, the qualified symbol name matches.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.config import get_config
from core.embedder import embedder_from_spec
from core.index_store import RepoIndex
from generation.llm_client import ExtractiveClient
from rag.engine import RagEngine
from retrieval.reranker import get_reranker

KS = (1, 3, 5, 10)


def _matches(chunk, spec: dict) -> bool:
    return chunk.path == spec["file"] and (spec.get("symbol") is None or chunk.name == spec["symbol"])


def _best_ranks(hits, relevant: list[dict]) -> list[int | None]:
    out = []
    for spec in relevant:
        out.append(next((i for i, h in enumerate(hits, 1) if _matches(h.chunk, spec)), None))
    return out


def evaluate(engine: RagEngine, questions: list[dict], modes=RagEngine.MODES, ks=KS) -> dict:
    answerable = [q for q in questions if q["relevant"]]
    results: dict = {}
    for mode in modes:
        rows = []
        for q in answerable:
            hits = engine.retrieve(q["question"], mode, top_k=max(ks))
            ranks = _best_ranks(hits, q["relevant"])
            row = {"type": q.get("type", "lookup"), "mrr": 1 / min(r for r in ranks if r) if any(ranks) else 0.0,
                   "ctx": sum(r is not None for r in ranks) / len(ranks)}
            for k in ks:
                row[f"r@{k}"] = sum(r is not None and r <= k for r in ranks) / len(ranks)
            rows.append(row)

        def mean(key: str, subset=None) -> float:
            sel = [r[key] for r in rows if subset is None or r["type"] == subset]
            return round(sum(sel) / len(sel), 3) if sel else float("nan")

        results[mode] = {**{f"Recall@{k}": mean(f"r@{k}") for k in ks}, "MRR": mean("mrr"), "CtxRecall": mean("ctx"),
                         "CtxRecall(relationship)": mean("ctx", "relationship"), "n": len(rows)}

    # guardrail behaviour uses the full pipeline (no LLM call needed: refusal happens before generation)
    def refused(question: str) -> bool:
        return not any(not h.relation for h in engine.retrieve(question, "full"))
    unans = [q for q in questions if not q["relevant"]]
    results["guard"] = {
        "false_refusals": round(sum(refused(q["question"]) for q in answerable) / max(1, len(answerable)), 3),
        "correct_refusals": round(sum(refused(q["question"]) for q in unans) / max(1, len(unans)), 3) if unans else None,
    }
    return results


def format_table(results: dict) -> str:
    cols = [c for c in next(iter(v for k, v in results.items() if k != "guard")) if c != "n"]
    lines = [f"{'mode':<15}" + "".join(f"{c:>26}" if "(" in c else f"{c:>11}" for c in cols)]
    for mode, r in results.items():
        if mode == "guard":
            continue
        lines.append(f"{mode:<15}" + "".join(f"{r[c]:>26}" if "(" in c else f"{r[c]:>11}" for c in cols))
    g = results["guard"]
    lines.append(f"\nGuardrail: false refusals on answerable Qs = {g['false_refusals']}, "
                 f"correct refusals on unanswerable Qs = {g['correct_refusals']}")
    return "\n".join(lines)


def load_engine(repo_dir: Path, cfg: dict) -> RagEngine:
    index = RepoIndex.load(repo_dir / "index")
    return RagEngine(index, embedder_from_spec(index.meta["embedder"], cfg), get_reranker(cfg), ExtractiveClient(), cfg)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-dir", required=True, help="e.g. data/indexed_repos/tiangolo__fastapi")
    ap.add_argument("--dataset", default=str(Path(__file__).with_name("eval_dataset.json")))
    ap.add_argument("--json", help="also write results to this file")
    args = ap.parse_args()
    cfg = get_config()
    engine = load_engine(Path(args.repo_dir), cfg)
    print(f"index: {engine.index.meta['repo']}  embedder={engine.index.meta['embedder'].get('model') or engine.index.meta['embedder']['backend']}"
          f"  reranker={engine.reranker.name}\n")
    data = json.loads(Path(args.dataset).read_text())
    results = evaluate(engine, data["questions"])
    print(format_table(results))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
