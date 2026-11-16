export function originalDownloadName(filename, fallback = 'spectrum.txt') {
  const name = (filename || fallback).replace(/[\\/]/g, '_');
  return name === '.' || name === '..' ? fallback : name;
}

export function batchDownloadNames(spectra) {
  const names = spectra.map(item => originalDownloadName(item.filename));
  const key = name => name.normalize('NFC').toLowerCase();
  const counts = new Map();
  names.forEach(name => counts.set(key(name), (counts.get(key(name)) || 0) + 1));
  // Duplicate names keep their filename and use separate ZIP directories.
  return names.map((name, index) => counts.get(key(name)) > 1 ? `${index + 1}/${name}` : name);
}
