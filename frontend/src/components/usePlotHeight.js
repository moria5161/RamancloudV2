import { useEffect, useRef, useState } from 'react';

export default function usePlotHeight() {
  const ref = useRef(null);
  const [height, setHeight] = useState(320);
  useEffect(() => {
    if (!ref.current) return undefined;
    let frame;
    const observer = new ResizeObserver(entries => {
      setHeight(Math.max(160, Math.floor(entries[0].contentRect.height)));
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    });
    observer.observe(ref.current);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, []);
  return [ref, height];
}
