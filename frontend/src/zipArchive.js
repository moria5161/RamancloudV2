import { localize } from './locale.js';
// ZIP32 store entries: PNG is already compressed; no runtime dependency is needed.
const utf8 = new TextEncoder();
const crcTable = Uint32Array.from({length:256}, (_, value) => {
  for (let bit=0; bit<8; bit++) value = value & 1 ? 0xedb88320 ^ value >>> 1 : value >>> 1;
  return value >>> 0;
});
function crc32(data) {
  let crc = 0xffffffff;
  for (const byte of data) crc = crcTable[(crc ^ byte) & 255] ^ crc >>> 8;
  return (crc ^ 0xffffffff) >>> 0;
}
export function createZip(entries) {
  if (!entries.length || entries.length > 65535) throw new Error(localize("导出文件数量无效。"));
  const local = [], central = [], names = new Set();
  let offset = 0, centralSize = 0;
  for (const entry of entries) {
    if (!entry.name || entry.name.startsWith('/') || /[\\:\x00]/.test(entry.name) || entry.name.split('/').some(part => !part || part === '.' || part === '..') || names.has(entry.name)) throw new Error(localize("导出文件名无效或重复。"));
    names.add(entry.name);
    const name = utf8.encode(entry.name), data = typeof entry.data === 'string' ? utf8.encode(entry.data) : entry.data;
    if (!(data instanceof Uint8Array) || data.byteLength >= 0xffffffff || name.length > 65535) throw new Error(localize("导出文件过大。"));
    const crc = crc32(data), header = new Uint8Array(30), view = new DataView(header.buffer);
    view.setUint32(0,0x04034b50,true); view.setUint16(4,20,true); view.setUint16(6,0x800,true);
    view.setUint16(12,0x21,true); view.setUint32(14,crc,true); view.setUint32(18,data.length,true); view.setUint32(22,data.length,true); view.setUint16(26,name.length,true);
    local.push(header,name,data);
    const record = new Uint8Array(46), recordView = new DataView(record.buffer);
    recordView.setUint32(0,0x02014b50,true); recordView.setUint16(4,20,true); recordView.setUint16(6,20,true); recordView.setUint16(8,0x800,true);
    recordView.setUint16(14,0x21,true); recordView.setUint32(16,crc,true); recordView.setUint32(20,data.length,true); recordView.setUint32(24,data.length,true); recordView.setUint16(28,name.length,true); recordView.setUint32(42,offset,true);
    central.push(record,name); centralSize += record.length + name.length; offset += header.length + name.length + data.length;
    if (offset + centralSize >= 0xffffffff) throw new Error(localize("导出包过大，请分批导出。"));
  }
  const end = new Uint8Array(22), endView = new DataView(end.buffer);
  endView.setUint32(0,0x06054b50,true); endView.setUint16(8,entries.length,true); endView.setUint16(10,entries.length,true); endView.setUint32(12,centralSize,true); endView.setUint32(16,offset,true);
  return new Blob([...local,...central,end],{type:'application/zip'});
}
