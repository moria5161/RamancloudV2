import { systemText } from '../locale.js';
import React from 'react';

// Illustrations for the explicitly labelled layout examples only. Production
// candidates will use RDKit depictions returned by the inference service.
export default function MoleculePreview({ molecule, label }) {
  const points = '100,37 142,61 142,109 100,133 58,109 58,61';
  return <svg className="sg-molecule" viewBox="0 0 220 165" role="img" aria-label={systemText(label)}>
    <g fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round">
      <polygon points={points} />
      {molecule.aromatic && <><path d="M106 49L132 65M132 104L106 120M68 103V67" /></>}
      {molecule.group && <path d="M142 61L165 47" />}
    </g>
    {molecule.group && <text x="169" y="48" fill="currentColor" fontSize="17" fontFamily="Arial, sans-serif">{molecule.group}</text>}
  </svg>;
}
