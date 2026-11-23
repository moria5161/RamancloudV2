import React, {createContext, useContext, useEffect, useRef, useState} from 'react';
import {Route, Routes, useLocation, useNavigate, UNSAFE_NavigationContext, parsePath} from 'react-router-dom';
import {Plus} from 'lucide-react';
import {apiErrorMessage} from '../auth';
import { usePreferences } from '../i18n';

const WorkspaceContext = createContext({reset:null,active:true});
export const useAnalysisWorkspace = () => useContext(WorkspaceContext);
export function useWorkspaceList(api,path,onData,onError,field) {
  const {active}=useAnalysisWorkspace();
  useEffect(()=>{
    if(!active)return;
    let cancelled=false;
    api.get(path).then(({data})=>{if(!cancelled)onData(field?data.data[field]:data);}).catch(error=>{if(!cancelled)onError?.(apiErrorMessage(error));});
    return()=>{cancelled=true;};
  },[api,path,active,onData,onError,field]);
}
export function NewAnalysisButton({disabled, beforeReset, txt, className}) {
  const { language } = usePreferences();
  const text = txt || ((zh, en) => language === 'zh' ? zh : en);
  const {reset} = useAnalysisWorkspace();
  return <button type="button" className={className} disabled={disabled} onClick={()=>{if (!beforeReset || beforeReset() !== false) reset?.();}}><Plus size={15}/><span>{text('新建分析','New analysis')}</span></button>;
}

// Each visited analysis owns its router location and mounted component tree.
// Its query, unfinished form, plot zoom and in-flight request survive navigation.
export default function AnalysisWorkspaces({pages, children}) {
  const location = useLocation(), navigate = useNavigate();
  const navigation = useContext(UNSAFE_NavigationContext);
  const cache = useRef(new Map()), previousPath = useRef(null), decision = useRef(null);
  const alive = useRef(true);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const [,render] = useState(0);
  const current = pages[location.pathname];
  const existing = cache.current.get(location.pathname);
  if (!decision.current || decision.current.key!==location.key) {
    const restore=!!current && previousPath.current !== location.pathname && !location.search && !!existing;
    decision.current={key:location.key,location:restore?existing.location:location,restore};
    previousPath.current=location.pathname;
  }
  const returning=decision.current.restore;
  if (current) cache.current.set(location.pathname,{location:decision.current.location,generation:existing?.generation || 0});
  const remembered = current ? cache.current.get(location.pathname).location : null;
  useEffect(()=>{
    if (returning && remembered.search) navigate({pathname:location.pathname,search:remembered.search},{replace:true});
  },[location.key]);
  useEffect(()=>{
    const frame=requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
    return ()=>cancelAnimationFrame(frame);
  },[location.pathname]);
  function reset(path) {
    const entry=cache.current.get(path);
    const fresh={...location,pathname:path,search:'',hash:'',state:null};
    cache.current.set(path,{location:fresh,generation:(entry?.generation || 0)+1});
    decision.current={key:location.key,location:fresh,restore:false};
    navigate(path,{replace:true});render(value=>value+1);
  }
  function navigatorFor(path) {
    const update=(method,to,state,options)=>{
      if (!alive.current) return;
      if (previousPath.current===path) return navigation.navigator[method](to,state,options);
      const target=typeof to==='string'?parsePath(to):to;
      let pathname=target.pathname || path;
      if (navigation.basename !== '/' && pathname.startsWith(navigation.basename)) pathname=pathname.slice(navigation.basename.length) || '/';
      if (pathname!==path) return;
      const previous=cache.current.get(path);
      if (!previous) return;
      cache.current.set(path,{...previous,location:{...previous.location,...target,pathname,state,key:crypto.randomUUID()}});
      render(value=>value+1);
    };
    return {...navigation.navigator,push:(...args)=>update('push',...args),replace:(...args)=>update('replace',...args)};
  }
  return <>{[...cache.current].map(([path,entry])=>{
    const Component=pages[path], active=path===location.pathname;
    return <section key={path} className="h-full" data-analysis-workspace={path} hidden={!active} aria-hidden={!active} style={{display:active?'block':'none'}}>
      <WorkspaceContext.Provider value={{active,reset:()=>reset(path)}}><UNSAFE_NavigationContext.Provider value={{...navigation,navigator:navigatorFor(path)}}><Routes location={entry.location}><Route path={path} element={<Component key={entry.generation}/>} /></Routes></UNSAFE_NavigationContext.Provider></WorkspaceContext.Provider>
    </section>;
  })}{!current && children}</>;
}
