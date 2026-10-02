import fs from 'node:fs';

// Derived from Natural Earth's public-domain 1:50m admin-0 GeoJSON.
// Supply the downloaded source path; retain region labels and simplified display geometry.
const source = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const round = value => Math.round(value * 1000) / 1000;
const countries = source.features.map(({ properties: p, geometry }) => ({
  code: p.ISO_A2_EH,
  center: [round(p.LABEL_X), round(p.LABEL_Y)],
  polygons: (geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates).map(polygon => polygon.map(ring => ring.map(pair => pair.map(round)))),
}));
fs.mkdirSync(new URL('../public/data/', import.meta.url), { recursive: true });
fs.writeFileSync(new URL('../public/data/world-countries.json', import.meta.url), JSON.stringify(countries));
console.log(`Prepared ${countries.length} regions`);
