"""Optional integration checks against the supplied local Agent package (no weights)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).parent))
from structure_profiles import configuration
from vib2mol_agent_package import installed_agent


@unittest.skipUnless(installed_agent(ROOT / '.runtime/vib2mol/source'), 'Install the supplied Agent archive first')
class AgentAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        cls.profile, cls.paths = configuration('agent')
        sys.path.insert(0, cls.paths['source'])
        grid = np.linspace(400, 4000, 1024)
        # A synthetic unit-test fixture, never a real prediction or a UI example.
        cls.spectrum = np.exp(-((grid - 1000) / 12) ** 2) + .7 * np.exp(-((grid - 1600) / 16) ** 2)

    def raw_candidates(self):
        return [dict(smiles='c1ccccc1', _kekule='C1=CC=CC=C1', generation_score=-3., matching_score=.2),
                dict(smiles='Oc1ccccc1', _kekule='OC1=CC=CC=C1', generation_score=-4., matching_score=.1)]

    def test_agent_uses_only_supplied_pool_and_preserves_matching_scores(self):
        from agent_adapter import enhance
        raw = self.raw_candidates()
        ordered, info, removed = enhance(raw, self.spectrum, dict(top_k=5, rerank=True, formula_counts={}), self.profile, self.paths['source'])
        self.assertEqual({c['smiles'] for c in ordered}, {c['smiles'] for c in raw})
        self.assertEqual({c['smiles']: c['matching_score'] for c in ordered}, {'c1ccccc1': .2, 'Oc1ccccc1': .1})
        self.assertFalse(info['llm_used'])
        self.assertEqual(info['route'], 'denovo')
        self.assertEqual(info['knowledge_profile'], 'sdbs_raman')
        self.assertTrue(info['references'])
        self.assertEqual(removed, 0)
        self.assertTrue(all(400 <= p['peak'] <= 4000 for p in info['peaks']))

    def test_formula_filter_never_fills_from_an_unmatched_candidate(self):
        from agent_adapter import enhance
        ordered, info, removed = enhance(self.raw_candidates(), self.spectrum,
                                        dict(top_k=5, rerank=True, formula_counts={'H': 6, 'C': 6}), self.profile, self.paths['source'])
        self.assertEqual([c['smiles'] for c in ordered], ['c1ccccc1'])
        self.assertEqual(removed, 1)
        self.assertEqual(info['route'], 'denovo_with_formula')
        self.assertFalse(info['knowledge_rerank_applied'])

    def test_empty_pool_has_no_invented_candidate_or_evidence(self):
        from agent_adapter import enhance
        ordered, info, removed = enhance([], self.spectrum, dict(top_k=5, rerank=True, formula_counts={}), self.profile, self.paths['source'])
        self.assertEqual(ordered, [])
        self.assertEqual(info['references'], [])
        self.assertEqual(removed, 0)

    def test_matching_disabled_does_not_claim_matching_was_called(self):
        from agent_adapter import enhance
        ordered, info, _ = enhance(self.raw_candidates(), self.spectrum, dict(top_k=5, rerank=False, formula_counts={}), self.profile, self.paths['source'])
        self.assertFalse(info['matching_enabled'])
        self.assertNotIn('rerank', info['tools_called'])
        self.assertFalse(info['knowledge_rerank_applied'])
        self.assertEqual([c['smiles'] for c in ordered], ['c1ccccc1', 'Oc1ccccc1'])


if __name__ == '__main__':
    unittest.main()
