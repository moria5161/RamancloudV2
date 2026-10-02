import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const position = (lon, lat, radius = 1) => {
  const a = THREE.MathUtils.degToRad(lon);
  const b = THREE.MathUtils.degToRad(lat);
  return new THREE.Vector3(Math.cos(b) * Math.cos(a), Math.sin(b), -Math.cos(b) * Math.sin(a)).multiplyScalar(radius);
};

function earthTexture(world, dark) {
  const canvas = document.createElement('canvas');
  canvas.width = 2048;
  canvas.height = 1024;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = dark ? '#183a48' : '#dceff5';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = dark ? '#315663' : '#c4dde7';
  ctx.lineWidth = 1;
  for (let i = 1; i < 12; i += 1) {
    ctx.beginPath(); ctx.moveTo(i * canvas.width / 12, 0); ctx.lineTo(i * canvas.width / 12, canvas.height); ctx.stroke();
  }
  for (let i = 1; i < 6; i += 1) {
    ctx.beginPath(); ctx.moveTo(0, i * canvas.height / 6); ctx.lineTo(canvas.width, i * canvas.height / 6); ctx.stroke();
  }
  ctx.fillStyle = dark ? '#659b91' : '#a2c8b9';
  ctx.strokeStyle = dark ? '#8bb6a7' : '#edf5ec';
  ctx.lineWidth = 0.7;
  for (const country of world) {
    for (const polygon of country.polygons) {
      ctx.beginPath();
      for (const ring of polygon) {
        ring.forEach(([lon, lat], index) => {
          const x = (lon + 180) / 360 * canvas.width;
          const y = (90 - lat) / 180 * canvas.height;
          if (!index) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.closePath();
      }
      ctx.fill('evenodd');
      ctx.stroke();
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export default function VisitorGlobeScene({ world, points, theme, playing, historical, apiRef, onSelect, onHover, onFailure, label }) {
  const host = useRef(null);
  const current = useRef({ playing, onSelect, onHover, onFailure });
  current.current = { playing, onSelect, onHover, onFailure };
  useEffect(() => {
    const element = host.current;
    let renderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' }); }
    catch { current.current.onFailure(); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.setClearColor(0, 0);
    renderer.domElement.setAttribute('aria-label', label);
    renderer.domElement.setAttribute('role', 'img');
    renderer.domElement.style.display = 'block';
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, .1, 100);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.enableZoom = false;
    controls.enableDamping = true;
    controls.dampingFactor = .08;
    controls.autoRotateSpeed = .55;
    const dark = theme === 'dark';
    const texture = earthTexture(world, dark);
    texture.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
    const earth = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), new THREE.MeshPhongMaterial({ map: texture, shininess: 9, specular: '#adcbd3' }));
    scene.add(earth);
    scene.add(new THREE.AmbientLight(0xffffff, 1.8));
    const light = new THREE.DirectionalLight(0xffffff, 2.2);
    light.position.set(-3, 4, -4);
    scene.add(light);
    const centers = new Map(world.map(country => [country.code, country.center]));
    const markers = [];
    const maximum = Math.max(1, ...points.map(point => point.count));
    for (const point of points) {
      const center = centers.get(point.code);
      if (!center) continue;
      const radius = .013 + .019 * Math.sqrt(Math.log1p(point.count) / Math.log1p(maximum));
      const marker = new THREE.Mesh(new THREE.SphereGeometry(radius, 16, 12), new THREE.MeshBasicMaterial({ color: historical ? '#dc8734' : '#147ddb' }));
      marker.position.copy(position(...center, 1.014));
      marker.userData = point;
      markers.push(marker);
      scene.add(marker);
      const ring = new THREE.Mesh(new THREE.RingGeometry(radius * 1.25, radius * 1.5, 32), new THREE.MeshBasicMaterial({ color: historical ? '#f0aa53' : '#46b7dd', transparent: true, opacity: .7, side: THREE.DoubleSide }));
      ring.position.copy(position(...center, 1.008));
      ring.lookAt(position(...center, 2));
      scene.add(ring);
    }
    let baseDistance = 3.6;
    camera.position.copy(position(105, 25, baseDistance));
    const resize = () => {
      const { width, height } = element.getBoundingClientRect();
      if (!width || !height) return;
      const ratio = camera.position.length() / baseDistance;
      camera.aspect = width / height;
      baseDistance = 1.13 / Math.sin(THREE.MathUtils.degToRad(19)) * Math.max(1, 1 / camera.aspect);
      camera.position.setLength(baseDistance * ratio);
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    let visible = false;
    const visibility = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
    visibility.observe(element);
    const raycaster = new THREE.Raycaster();
    let hovered = null;
    let down = null;
    const pick = event => {
      const rect = renderer.domElement.getBoundingClientRect();
      raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, 1 - (event.clientY - rect.top) / rect.height * 2), camera);
      const hit = raycaster.intersectObjects([earth, ...markers])[0];
      return hit && hit.object !== earth ? hit.object.userData : null;
    };
    const move = event => {
      const point = pick(event);
      if (hovered?.code !== point?.code) { hovered = point; current.current.onHover(point); }
      renderer.domElement.style.cursor = point ? 'pointer' : 'grab';
    };
    const leave = () => { hovered = null; current.current.onHover(null); };
    const start = event => { down = [event.clientX, event.clientY]; };
    const end = event => {
      if (down && Math.hypot(event.clientX - down[0], event.clientY - down[1]) < 5) {
        const point = pick(event);
        if (point) current.current.onSelect(point.code);
      }
      down = null;
    };
    const contextLost = event => { event.preventDefault(); current.current.onFailure(); };
    renderer.domElement.addEventListener('pointermove', move);
    renderer.domElement.addEventListener('pointerleave', leave);
    renderer.domElement.addEventListener('pointerdown', start);
    renderer.domElement.addEventListener('pointerup', end);
    renderer.domElement.addEventListener('webglcontextlost', contextLost);
    apiRef.current = {
      reset: () => { camera.position.copy(position(105, 25, baseDistance)); controls.update(); },
      zoom: factor => camera.position.setLength(THREE.MathUtils.clamp(camera.position.length() * factor, baseDistance * .7, baseDistance * 1.7)),
      focus: code => { const center = centers.get(code); if (center) { camera.position.copy(position(...center, camera.position.length())); controls.update(); } },
    };
    let previous = 0;
    renderer.setAnimationLoop(now => {
      if (!visible || document.hidden || now - previous < 32) return;
      const delta = Math.min((now - previous) / 1000, .1);
      previous = now;
      controls.autoRotate = current.current.playing && !hovered;
      controls.update(delta);
      renderer.render(scene, camera);
    });
    return () => {
      apiRef.current = null;
      renderer.setAnimationLoop(null);
      observer.disconnect(); visibility.disconnect(); controls.dispose();
      renderer.domElement.removeEventListener('webglcontextlost', contextLost);
      renderer.domElement.remove();
      scene.traverse(object => { object.geometry?.dispose(); object.material?.dispose(); });
      texture.dispose(); renderer.dispose(); renderer.forceContextLoss();
    };
  }, [world, points, theme, historical, apiRef, label]);
  return <div ref={host} className="visitor-globe-canvas" />;
}
