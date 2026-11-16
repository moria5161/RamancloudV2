import React, { useLayoutEffect, useRef, useState } from 'react';

export default function ChartViewport({ children, className = '' }) {
  const ref = useRef(null);
  const [height, setHeight] = useState(300);
  useLayoutEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width && entry.contentRect.height) setHeight(Math.round(entry.contentRect.height));
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return <div ref={ref} className={`chart-viewport h-full min-h-0 min-w-0 ${className}`}>{children(height)}</div>;
}
