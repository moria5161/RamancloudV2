"""Adapt the supplied Agent to validated Ramancloud inference and frozen inputs."""
from argparse import Namespace
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace


def enhance(candidates, values, payload, profile, source):
    from vib2mol_agent.core.agent import Vib2MolAgent
    from vib2mol_agent.core.planner import RulePlanner
    from vib2mol_agent.core.schemas import Candidate, TaskContext, ToolResult
    from vib2mol_agent.runtime.book_rag import retrieve_book_context
    from vib2mol_agent.runtime.rag.legacy_engine import apply_confidence_second_rerank
    from vib2mol_agent.tools.raman_knowledge import extract_top_peaks

    # Formula is a post-generation guard. Do not silently send it to a checkpoint
    # that was trained without formula conditioning, or read target SMILES.
    counts = payload.get('formula_counts') or {}
    elements = sorted(counts)
    if 'C' in elements:
        elements = ['C'] + (['H'] if 'H' in counts else []) + [e for e in elements if e not in ('C', 'H')]
    formula = ''.join(element + (str(counts[element]) if counts[element] != 1 else '') for element in elements) or None
    task = TaskContext(spectrum_type='raman', formula=formula, top_k=profile['beam_size'],
                       metadata=dict(disable_formula_index_supplement=True, requested_top_k=payload['top_k'],
                                     formula_conditioning=False, source='ramancloud_validated_input'))
    generated = [Candidate(rank=i + 1, smiles=c['_kekule'], score=c['generation_score'], source='vib2mol_denovo',
                           valid=True, metadata={'raw_index': i}) for i, c in enumerate(candidates)]

    class GenerationTool:
        def run(self, **kwargs):
            return ToolResult(sample_id=task.sample_id, task='de_novo_generation', spectrum_type='raman',
                              formula=formula, tools_called=['de_novo_generation'], candidates=generated,
                              metadata={'generation_adapter': 'strict_verified_checkpoint', 'formula_conditioning': False})

    class MatchingTool:
        def run(self, candidates, top_k, **kwargs):
            for c in candidates:
                c.score = candidates_by_index[c.metadata['raw_index']]['matching_score']
            return sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]

    candidates_by_index = dict(enumerate(candidates))
    agent = Vib2MolAgent(denovo_tool=GenerationTool(),
                        rerank_tool=MatchingTool() if payload.get('rerank') else None, planner=RulePlanner())
    result = agent.run_task(task, spectrum=values)
    response = SimpleNamespace(result=result, plan=RulePlanner().plan(task), intent=SimpleNamespace(task=task))
    data = Path(source) / 'vib2mol_agent/data'
    manual = list(data.glob('IR_Raman_*.md'))
    args = Namespace(ds='mols', spectral_types='raman', second_rerank='rag' if payload.get('rerank') else 'none',
                     confidence_threshold=.8, book_rag=True, book_rag_confidence_threshold=1.1,
                     book_rag_index=str(data / profile['rag_index']), book_rag_top_k=4,
                     posterior_top_n_peaks=20, rag_profile=profile['rag_profile'],
                     rag_rerank_weight=profile['rag_weight'], raman_rag_rerank_min_delta=profile['rag_min_delta'],
                     spectral_manual_rules_path=str(data / 'spectral_manual_rules_v1.json'),
                     spectral_manual_path=str(manual[0]) if manual else None,
                     raman_evidence_cards_path=str(data / 'raman_evidence_cards_v1.json'))
    sample = {'raman': values}  # Unknown sample: no dataset labels or target structure.
    if result.candidates:
        apply_confidence_second_rerank(args, response, sample)
        # A single candidate cannot be reranked, but can still have referenced evidence.
        if 'book_rag' not in result.metadata:
            retrieve_book_context(args, response, sample)
    secondary = result.metadata.get('second_rerank', {})
    records = {row['smiles']: row for row in secondary.get('rag_score_records', [])}
    ordered = []
    for c in result.candidates:
        raw = candidates_by_index[c.metadata['raw_index']]
        evidence = records.get(c.smiles, {})
        raw['agent_evidence'] = {key: evidence[key] for key in ('combined_score', 'rag_support', 'manual_evidence_score', 'manual_evidence_group') if key in evidence}
        raw['agent_evidence']['previous_matching_rank'] = c.metadata.get('pre_second_rerank_rank', c.rank)
        ordered.append(raw)
    snippets = []
    for item in result.metadata.get('book_rag', {}).get('snippets', []):
        source_name = PureWindowsPath(str(item.get('source') or '')).name
        if 'COURSE NOTES ON' in source_name:
            source_name = source_name[source_name.index('COURSE NOTES ON'):]
        snippets.append(dict(id=item.get('id'), page=item.get('page'), source=source_name,
                             spectral_modality=item.get('spectral_modality'),
                             excerpt=str(item.get('text') or '')[:260],
                             wavenumbers=item.get('wavenumbers', [])[:12]))
    metadata = dict(enabled=True, planner='rule', llm_used=False, route=result.metadata['route'],
                    tools_called=[tool for tool in result.tools_called if tool != 'rerank' or payload.get('rerank')],
                    matching_enabled=bool(payload.get('rerank')), formula_mode='post_filter',
                    knowledge_profile=profile['rag_profile'], knowledge_rerank_applied=bool(secondary.get('applied')),
                    knowledge_rerank_reason=secondary.get('reason', 'No valid candidates'),
                    references=snippets,
                    peaks=extract_top_peaks(values, top_n=12, min_wavenumber=400, max_wavenumber=4000,
                                            wavenumber_start=400, wavenumber_step=None),
                    note='本地规则与知识索引用于辅助排序；不是新的微调权重，也不是结构鉴定结论。')
    return ordered, metadata, len(candidates) - len(ordered)
