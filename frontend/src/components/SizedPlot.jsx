import React, {useCallback,useEffect,useRef} from 'react';
import Plot from 'react-plotly.js';
import Plotly from 'plotly.js/dist/plotly';

// Plotly SVGs are positioned absolutely. Reserve their full height in normal
// document flow before mounting, including when a tab or cached page reopens.
export default function SizedPlot({layout={},style={},onInitialized,onUpdate,onClick,...props}) {
  const host=useRef(null), graph=useRef(null), frame=useRef(null);
  const click=useRef(onClick);
  click.current=onClick;
  const handlePlotClick=useCallback(event=>click.current?.(event),[]);
  const height=Number.isFinite(layout.height)?layout.height:500;
  function bindGraph(div) {
    graph.current=div;
    // Plotly can recreate the emitter while the React component keeps its props.
    div.removeListener('plotly_click',handlePlotClick);
    if(onClick) div.on('plotly_click',handlePlotClick);
  }
  function resize() {
    cancelAnimationFrame(frame.current);
    frame.current=requestAnimationFrame(()=>{
      const bounds=host.current?.getBoundingClientRect();
      if(graph.current && bounds?.width>0 && bounds?.height>0 && !host.current.closest('[hidden],[aria-hidden="true"]')) {
        Promise.resolve(Plotly.Plots.resize(graph.current)).catch(()=>{});
      }
    });
  }
  useEffect(()=>{
    const observer=new ResizeObserver(resize);
    if(host.current)observer.observe(host.current);
    return()=>{observer.disconnect();cancelAnimationFrame(frame.current);graph.current=null;};
  },[]);
  return <div ref={host} className="sized-plot" style={{...style,display:'block',position:'relative',width:style.width || '100%',height,minHeight:height,minWidth:0,flexShrink:0}}>
    <Plot {...props} layout={{...layout,autosize:true,height}} style={{width:'100%',height}} useResizeHandler={false}
      onInitialized={(figure,div)=>{bindGraph(div);resize();onInitialized?.(figure,div);}}
      onUpdate={(figure,div)=>{bindGraph(div);onUpdate?.(figure,div);}}/>
  </div>;
}
