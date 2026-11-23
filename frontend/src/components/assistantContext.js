export function samplePreview(matrix, maximum = 64) {
  if (!Array.isArray(matrix) || !matrix.length || !Array.isArray(matrix[0]) || !matrix[0].length) return undefined;
  const rowStride = Math.max(1, Math.ceil(matrix.length / maximum));
  const columnStride = Math.max(1, Math.ceil(matrix[0].length / maximum));
  return matrix.filter((_, index) => index % rowStride === 0).map(row => row.filter((_, index) => index % columnStride === 0));
}
