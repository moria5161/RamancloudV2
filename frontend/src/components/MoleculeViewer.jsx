import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { TrackballControls } from 'three/examples/jsm/controls/TrackballControls.js';
import { Pause, RotateCcw, Rotate3D } from 'lucide-react';
import { usePreferences } from '../i18n';

const colors = { H: 0xe5e7eb, C: 0x606875, N: 0x397ee8, O: 0xe44d51, F: 0x56bd69, P: 0xe7953d, S: 0xe9c83f, Cl: 0x4db96b, Br: 0xb65c47 };

export default function MoleculeViewer({ molecule }) {
  const { t, theme } = usePreferences();
  const host = useRef(null);
  const viewer = useRef(null);
  const [rotating, setRotating] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    let renderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); }
    catch { setFailed(true); return; }
    const container = host.current;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 1000);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 2));
    const light = new THREE.DirectionalLight(0xffffff, 2.2);
    light.position.set(6, 8, 10);
    scene.add(light);
    const group = new THREE.Group();
    scene.add(group);
    const materials = new Map();
    const material = element => {
      if (!materials.has(element)) materials.set(element, new THREE.MeshStandardMaterial({
        color: colors[element] || 0xb575cb, roughness: 0.35, metalness: 0.05,
      }));
      return materials.get(element);
    };
    const sphere = new THREE.SphereGeometry(1, 24, 16);
    const cylinder = new THREE.CylinderGeometry(0.1, 0.1, 1, 12);
    const points = molecule.atoms.map(atom => new THREE.Vector3(...atom.position));
    const bounds = new THREE.Box3().setFromPoints(points);
    const center = bounds.getCenter(new THREE.Vector3());
    const radius = bounds.getSize(new THREE.Vector3()).length() / 2 + 0.65;
    molecule.atoms.forEach((atom, index) => {
      const mesh = new THREE.Mesh(sphere, material(atom.element));
      mesh.position.copy(points[index]).sub(center);
      mesh.scale.setScalar(atom.element === 'H' ? 0.23 : 0.38);
      group.add(mesh);
    });
    const up = new THREE.Vector3(0, 1, 0);
    molecule.bonds.forEach(([a, b]) => {
      const start = points[a].clone().sub(center);
      const end = points[b].clone().sub(center);
      const middle = start.clone().lerp(end, 0.5);
      [[start, middle, molecule.atoms[a].element], [middle, end, molecule.atoms[b].element]].forEach(([p, q, element]) => {
        const mesh = new THREE.Mesh(cylinder, material(element));
        const direction = q.clone().sub(p);
        mesh.position.copy(p).lerp(q, 0.5);
        mesh.scale.y = direction.length();
        mesh.quaternion.setFromUnitVectors(up, direction.normalize());
        group.add(mesh);
      });
    });
    camera.position.set(0, 0, radius * 3);
    const controls = new TrackballControls(camera, renderer.domElement);
    controls.rotateSpeed = 2;
    controls.staticMoving = true;
    controls.keys = [];
    controls.minDistance = radius * 1.2;
    controls.maxDistance = radius * 10;
    let interacting = false;
    controls.addEventListener('start', () => { interacting = true; });
    controls.addEventListener('end', () => { interacting = false; });
    const fit = () => {
      controls.reset();
      const angle = Math.min(THREE.MathUtils.degToRad(camera.fov / 2), Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect));
      camera.position.set(0, 0, radius / Math.sin(angle) * 1.1);
      camera.up.set(0, 1, 0);
      controls.target.set(0, 0, 0);
      controls.update();
    };
    const resize = () => {
      const { width, height } = container.getBoundingClientRect();
      if (!width || !height) return;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
      controls.handleResize();
      fit();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    viewer.current = { controls, fit, autoRotate: false };
    let frame;
    let lastTime = performance.now();
    const render = () => {
      frame = requestAnimationFrame(render);
      const now = performance.now();
      const elapsed = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;
      if (!container.offsetWidth || !container.offsetHeight) return;
      if (viewer.current?.autoRotate && !interacting) {
        const angle = elapsed * 2 * Math.PI / 60 * 1.3;
        camera.position.sub(controls.target).applyAxisAngle(up, angle).add(controls.target);
        camera.up.applyAxisAngle(up, angle);
      }
      controls.update();
      renderer.render(scene, camera);
    };
    render();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      sphere.dispose(); cylinder.dispose();
      materials.forEach(value => value.dispose());
      renderer.dispose();
      renderer.domElement.remove();
      viewer.current = null;
    };
  }, [molecule]);

  useEffect(() => { if (viewer.current) viewer.current.autoRotate = rotating; }, [rotating, molecule]);

  return <div className="molecule-viewer" data-theme={theme}>
    <div ref={host} className="molecule-canvas" role="img" aria-label={`${t('conformer')}: ${molecule.formula}`} />
    {failed && <p role="alert" className="absolute inset-0 grid place-items-center text-sm text-gray-400">WebGL unavailable</p>}
    <div className="absolute right-3 top-3 flex gap-2">
      <button className="molecule-tool" title={t(rotating ? 'pauseRotation' : 'rotateMolecule')} aria-label={t(rotating ? 'pauseRotation' : 'rotateMolecule')} aria-pressed={rotating} onClick={() => setRotating(value => !value)}>
        {rotating ? <Pause className="w-4 h-4" /> : <Rotate3D className="w-4 h-4" />}
      </button>
      <button className="molecule-tool" title={t('resetMoleculeView')} aria-label={t('resetMoleculeView')} onClick={() => viewer.current?.fit()}><RotateCcw className="w-4 h-4" /></button>
    </div>
    <span className="absolute bottom-4 left-4 text-sm text-gray-400">{molecule.formula}</span>
  </div>;
}
