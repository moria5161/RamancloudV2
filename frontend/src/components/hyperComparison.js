export const HYPERSPECTRAL_COLORSCALE='Jet';
export function heatmapLimits(...matrices) {
  let low=Infinity,high=-Infinity;
  for(const matrix of matrices) for(const row of matrix || []) for(const value of Array.isArray(row)?row:[]) {
    if(Number.isFinite(value)){low=Math.min(low,value);high=Math.max(high,value);}
  }
  if(low===Infinity)return {zmin:0,zmax:1};
  return {zmin:low,zmax:high===low?low+(Math.abs(low)*1e-6 || 1):high};
}
