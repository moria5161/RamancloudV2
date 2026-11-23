// Small, text-only formatting subset. Never interprets model output as HTML.
export function inlineParts(text) {
  return String(text).split(/(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^\s*\n](?:[^*\n]*[^\s*\n])?\*)/g).filter(Boolean).map(value => {
    if (/^`[^`\n]+`$/.test(value)) return { type: 'code', text: value.slice(1, -1) };
    if (/^(?:\*\*[^*\n]+\*\*|__[^_\n]+__)$/.test(value)) return { type: 'strong', text: value.slice(2, -2) };
    if (/^\*[^\s*\n](?:[^*\n]*[^\s*\n])?\*$/.test(value)) return { type: 'em', text: value.slice(1, -1) };
    return { type: 'text', text: value };
  });
}

export function answerBlocks(text) {
  const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n'), blocks = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i], value = line.trim();
    if (!value || /^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)) continue;
    if (/^\s*```/.test(line)) {
      const code = [];
      while (++i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i]);
      blocks.push({ type: 'code', text: code.join('\n') }); continue;
    }
    if (value.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i+1])) {
      const cells = row => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
      const rows = [cells(line)]; i++;
      while (i+1 < lines.length && lines[i+1].includes('|') && lines[i+1].trim()) rows.push(cells(lines[++i]));
      blocks.push({ type: 'table', rows }); continue;
    }
    const heading = line.match(/^\s{0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$/);
    if (heading) { blocks.push({ type: 'heading', text: heading[1] }); continue; }
    const item = line.match(/^\s*(?:[-*+]\s+|(\d+)[.)、]\s*)(.+)$/);
    if (item) { blocks.push({ type: 'item', number: item[1], text: item[2] }); continue; }
    if (/^\s*>\s?/.test(line)) { blocks.push({ type: 'quote', text: line.replace(/^\s*>\s?/, '') }); continue; }
    blocks.push({ type: 'paragraph', text: line });
  }
  return blocks;
}

export function plainAnswer(text) {
  const inline = value => inlineParts(value).map(p => p.text).join('');
  return answerBlocks(text).map(block => {
    if (block.type === 'code') return block.text;
    if (block.type === 'table') return block.rows.map(row => row.map(inline).join('\t')).join('\n');
    return (block.type === 'item' ? `${block.number ? block.number + '.' : '•'} ` : '') + inline(block.text);
  }).join('\n\n');
}
