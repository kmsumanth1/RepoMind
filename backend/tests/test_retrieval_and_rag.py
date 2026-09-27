def _files(hits):
    return [h.chunk.path for h in hits]


def test_index_metadata(built_index):
    m = built_index.meta
    assert m["num_files"] == 6 and m["num_chunks"] >= 12 and m["embedder"]["backend"] == "hashing"
    assert built_index.vectors.shape[0] == len(built_index.chunks)


def test_hybrid_finds_relevant_code(engine):
    hits = engine.retrieve("How does the rate limiter work?", "hybrid")
    assert "app/ratelimit.py" in _files(hits[:3])
    hits = engine.retrieve("how are tokens verified", "bm25")
    assert hits[0].chunk.path == "app/auth.py"


def test_exact_identifier_lookup(engine):
    hits = engine.retrieve("explain `create_token`", "hybrid")
    assert hits[0].chunk.name == "create_token"
    hits = engine.retrieve("what is in ratelimit.py", "hybrid")
    assert set(_files(hits[:3])) == {"app/ratelimit.py"}          # the file has exactly 3 chunks


def test_every_ablation_mode_runs(engine):
    for mode in engine.MODES:
        assert engine.retrieve("verify token signature", mode)


def test_guardrail_refuses_unrelated_question(engine):
    out = engine.answer("How do I bake sourdough bread?")
    assert out.refused and not out.citations and "couldn't find" in out.answer


def test_blended_refusal_phrase_with_real_citations_is_not_refused(engine):
    """Some models prepend the refusal sentence ("I couldn't find...") even while going on
    to give a real, cited answer - despite the prompt telling them not to (regression for a
    real bug: this used to make the app hide valid citations and show a false refusal)."""
    from generation.llm_client import LLMClient

    class BlendedLLM(LLMClient):
        name = "fake:blended"

        def answer(self, prompt, max_tokens=1024):
            n = prompt.sources[0].n
            return (f"I couldn't find enough in the indexed code to answer that fully, but "
                    f"here is what's available: it uses token verification [{n}].")

    original_llm = engine.llm
    engine.llm = BlendedLLM()
    try:
        out = engine.answer("how are tokens verified")
    finally:
        engine.llm = original_llm
    assert out.refused is False
    assert out.grounded is True
    assert out.citations


def test_answer_has_valid_citations(engine):
    out = engine.answer("How does the rate limiter work?")
    assert out.grounded and out.citations
    assert any(c.file == "app/ratelimit.py" for c in out.citations)
    for c in out.citations:
        assert 1 <= c.start_line <= c.end_line


def test_graph_expansion_adds_callers_for_impact_questions(engine, built_index):
    from retrieval.graph_expansion import expand
    from retrieval.hybrid_search import Hit
    pos = built_index.name_index["verify_token"][0]
    seed = Hit(pos=pos, chunk=built_index.chunks[pos], relevance=1.0)
    added = expand(built_index, [seed], "What would break if I change verify_token?")
    assert [(h.chunk.name, h.relation) for h in added] == [("handle_request", "calls verify_token")]
    assert expand(built_index, [seed], "how does verify_token check the signature") == []     # not a relationship question


def test_impact_answer_cites_callers(engine):
    out = engine.answer("What would break if I change verify_token?")
    assert {"verify_token", "handle_request"} <= {c.name for c in out.citations}
    plain = engine.retrieve("verify_token signature", "full")
    assert not any(h.relation for h in plain)


def test_follow_up_is_condensed(engine):
    hist = [{"role": "user", "content": "How does the rate limiter work?"}, {"role": "assistant", "content": "..."}]
    assert "rate limiter" in engine.condense("what about its window?", hist)
