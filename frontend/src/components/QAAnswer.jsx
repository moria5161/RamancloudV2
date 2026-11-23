import React from 'react';
import { answerBlocks, inlineParts } from './qaAnswer.js';

function Inline({ text }) {
  return inlineParts(text).map((part, i) => part.type === 'strong' ? <strong key={i}>{part.text}</strong>
    : part.type === 'em' ? <em key={i}>{part.text}</em>
    : part.type === 'code' ? <code key={i}>{part.text}</code> : <React.Fragment key={i}>{part.text}</React.Fragment>);
}

export default function QAAnswer({ text }) {
  const blocks = answerBlocks(text), output = [];
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    if (block.type === 'item') {
      const ordered = Boolean(block.number), items = [block];
      while (blocks[i+1]?.type === 'item' && Boolean(blocks[i+1].number) === ordered) items.push(blocks[++i]);
      const Tag = ordered ? 'ol' : 'ul';
      output.push(<Tag key={i} start={ordered ? Number(block.number) : undefined}>{items.map((item, n) => <li key={n} value={ordered ? Number(item.number) : undefined}><Inline text={item.text} /></li>)}</Tag>);
    } else if (block.type === 'heading') output.push(<h4 key={i}><Inline text={block.text} /></h4>);
    else if (block.type === 'code') output.push(<pre key={i}><code>{block.text}</code></pre>);
    else if (block.type === 'quote') output.push(<blockquote key={i}><Inline text={block.text} /></blockquote>);
    else if (block.type === 'table') output.push(<div className="qa-answer-table" key={i}><table><thead><tr>{block.rows[0].map((cell, n) => <th key={n}><Inline text={cell} /></th>)}</tr></thead><tbody>{block.rows.slice(1).map((row, n) => <tr key={n}>{row.map((cell, c) => <td key={c}><Inline text={cell} /></td>)}</tr>)}</tbody></table></div>);
    else output.push(<p key={i}><Inline text={block.text} /></p>);
  }
  return <div className="qa-answer">{output}</div>;
}
