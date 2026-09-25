import React, { useEffect, useRef, useState } from 'react';
import { Play, Pause, RotateCcw, Globe as GlobeIcon } from 'lucide-react';

interface Globe3DProps {
  events?: Array<{ id: string; lat: number; lon: number; severity: string; type: string }>;
}

export const Globe3D: React.FC<Globe3DProps> = ({ events = [] }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [showGrid, setShowGrid] = useState<boolean>(true);
  const [showHeatmap, setShowHeatmap] = useState<boolean>(true);

  // Mouse interaction state
  const isDraggingRef = useRef<boolean>(false);
  const previousMousePositionRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const rotationRef = useRef<{ x: number; y: number }>({ x: 0.3, y: -0.8 });
  const zoomRef = useRef<number>(1.0);

  // Default demo events if empty
  const demoEvents = events.length > 0 ? events : [
    { id: 'EVT-001', lat: 18.5, lon: 86.2, severity: 'SEVERE', type: 'CYCLONIC_STORM' },
    { id: 'EVT-002', lat: 14.2, lon: 82.5, severity: 'MODERATE', type: 'HEAVY_PRECIPITATION' },
    { id: 'EVT-003', lat: 21.8, lon: 88.5, severity: 'SEVERE', type: 'HIGH_WIND' },
  ];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let animTime = 0;

    const render = () => {
      animTime += 0.03;
      const width = canvas.width;
      const height = canvas.height;
      const radius = Math.min(width, height) * 0.32 * zoomRef.current;
      const centerX = width / 2;
      const centerY = height / 2;

      ctx.clearRect(0, 0, width, height);

      // 1. Space background with stars
      ctx.fillStyle = '#050a14';
      ctx.fillRect(0, 0, width, height);

      // Starfield dots
      ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
      for (let i = 0; i < 60; i++) {
        const sx = (Math.sin(i * 99 + 1) * 0.5 + 0.5) * width;
        const sy = (Math.cos(i * 33 + 2) * 0.5 + 0.5) * height;
        const sSize = (i % 3 === 0) ? 1.5 : 1.0;
        ctx.beginPath();
        ctx.arc(sx, sy, sSize, 0, Math.PI * 2);
        ctx.fill();
      }

      // Auto rotation
      const rotSpeed = isPlaying ? 0.003 : 0;
      if (isPlaying && !isDraggingRef.current) {
        rotationRef.current.y += rotSpeed;
      }

      const rotX = rotationRef.current.x;
      const rotY = rotationRef.current.y;

      // 2. Outer Atmospheric Glow
      const glowGrad = ctx.createRadialGradient(centerX, centerY, radius * 0.95, centerX, centerY, radius * 1.25);
      glowGrad.addColorStop(0, 'rgba(6, 182, 212, 0.35)');
      glowGrad.addColorStop(0.5, 'rgba(14, 165, 233, 0.15)');
      glowGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = glowGrad;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius * 1.25, 0, Math.PI * 2);
      ctx.fill();

      // 3. Globe Ocean Sphere Base
      const sphereGrad = ctx.createRadialGradient(
        centerX - radius * 0.3, centerY - radius * 0.3, radius * 0.1,
        centerX, centerY, radius
      );
      sphereGrad.addColorStop(0, '#0e2a47');
      sphereGrad.addColorStop(0.7, '#071629');
      sphereGrad.addColorStop(1, '#020914');

      ctx.save();
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.fillStyle = sphereGrad;
      ctx.fill();
      ctx.clip();

      // Helper function to project lat/lon to 3D sphere screen coords
      const project3D = (lat: number, lon: number) => {
        const phi = (90 - lat) * (Math.PI / 180);
        const theta = (lon + 180) * (Math.PI / 180) + rotY;

        // Spherical coordinates
        let x = Math.sin(phi) * Math.sin(theta);
        let y = Math.cos(phi);
        let z = Math.sin(phi) * Math.cos(theta);

        // Apply pitch tilt (rotX)
        const cosX = Math.cos(rotX);
        const sinX = Math.sin(rotX);
        const y2 = y * cosX - z * sinX;
        const z2 = y * sinX + z * cosX;

        const screenX = centerX + x * radius;
        const screenY = centerY - y2 * radius;
        const visible = z2 > -0.15; // Front hemisphere check

        return { x: screenX, y: screenY, z: z2, visible };
      };

      // 4. Lat/Lon Grid Lines
      if (showGrid) {
        ctx.strokeStyle = 'rgba(6, 182, 212, 0.18)';
        ctx.lineWidth = 1;

        // Latitude circles
        for (let lat = -60; lat <= 60; lat += 30) {
          ctx.beginPath();
          let started = false;
          for (let lon = -180; lon <= 180; lon += 5) {
            const p = project3D(lat, lon);
            if (p.visible) {
              if (!started) { ctx.moveTo(p.x, p.y); started = true; }
              else { ctx.lineTo(p.x, p.y); }
            } else {
              started = false;
            }
          }
          ctx.stroke();
        }

        // Longitude meridians
        for (let lon = -180; lon < 180; lon += 30) {
          ctx.beginPath();
          let started = false;
          for (let lat = -80; lat <= 80; lat += 5) {
            const p = project3D(lat, lon);
            if (p.visible) {
              if (!started) { ctx.moveTo(p.x, p.y); started = true; }
              else { ctx.lineTo(p.x, p.y); }
            } else {
              started = false;
            }
          }
          ctx.stroke();
        }
      }

      // 5. Stylized India Landmass Outline / Polygon points approximation
      const indiaOutline = [
        [35.0, 77.0], [32.0, 76.0], [28.0, 70.0], [24.0, 68.5], [20.0, 72.8],
        [15.0, 73.8], [10.0, 76.0], [8.0, 77.5], [10.0, 79.8], [13.0, 80.2],
        [16.0, 82.0], [20.0, 86.5], [22.0, 89.0], [26.0, 89.8], [27.5, 95.0],
        [29.0, 92.0], [27.0, 88.0], [30.0, 80.0], [35.0, 77.0]
      ];

      ctx.beginPath();
      let startedLand = false;
      for (const point of indiaOutline) {
        const lat = point[0];
        const lon = point[1];
        if (lat === undefined || lon === undefined) continue;
        const p = project3D(lat, lon);
        if (p.visible) {
          if (!startedLand) { ctx.moveTo(p.x, p.y); startedLand = true; }
          else { ctx.lineTo(p.x, p.y); }
        }
      }
      ctx.closePath();
      ctx.fillStyle = 'rgba(6, 182, 212, 0.12)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(6, 182, 212, 0.45)';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // 6. Weather Anomaly Heatmap Layer
      if (showHeatmap) {
        for (let i = 0; i < 15; i++) {
          const lat = 10 + (i % 5) * 3 + Math.sin(animTime * 0.5 + i) * 1.5;
          const lon = 80 + Math.floor(i / 5) * 4 + Math.cos(animTime * 0.5 + i) * 1.5;
          const p = project3D(lat, lon);
          if (p.visible) {
            const hGrad = ctx.createRadialGradient(p.x, p.y, 2, p.x, p.y, 24);
            const isSevere = i % 3 === 0;
            hGrad.addColorStop(0, isSevere ? 'rgba(239, 68, 68, 0.6)' : 'rgba(245, 158, 11, 0.4)');
            hGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
            ctx.fillStyle = hGrad;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 24, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      // 7. 3D Animated Event Pulse Markers & Columns
      demoEvents.forEach((evt) => {
        const p = project3D(evt.lat, evt.lon);
        if (p.visible) {
          const isSevere = evt.severity === 'SEVERE';
          const color = isSevere ? '#ef4444' : '#f59e0b';

          // Vertical pulse column
          const colHeight = 35 + Math.sin(animTime * 3) * 6;
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p.x, p.y - colHeight);
          ctx.stroke();

          // Column top dot
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(p.x, p.y - colHeight, 5 + Math.sin(animTime * 4) * 1.5, 0, Math.PI * 2);
          ctx.fill();

          // Expanding ground pulse ring
          const ringRadius = (animTime * 15 + evt.lat * 5) % 20;
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5 * (1 - ringRadius / 20);
          ctx.beginPath();
          ctx.arc(p.x, p.y, ringRadius, 0, Math.PI * 2);
          ctx.stroke();

          // Label
          ctx.fillStyle = '#f8fafc';
          ctx.font = '11px JetBrains Mono, monospace';
          ctx.fillText(`${evt.id} (${evt.severity})`, p.x + 8, p.y - colHeight);
        }
      });

      ctx.restore();

      // Equator / Specular Highlight overlay
      const specGrad = ctx.createRadialGradient(
        centerX - radius * 0.4, centerY - radius * 0.4, 0,
        centerX, centerY, radius
      );
      specGrad.addColorStop(0, 'rgba(255, 255, 255, 0.08)');
      specGrad.addColorStop(0.5, 'rgba(255, 255, 255, 0.02)');
      specGrad.addColorStop(1, 'rgba(0, 0, 0, 0.4)');
      ctx.fillStyle = specGrad;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.fill();

      // Border ring
      ctx.strokeStyle = 'rgba(6, 182, 212, 0.5)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.stroke();

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [isPlaying, showGrid, showHeatmap, demoEvents]);

  // Mouse drag Orbit Controls
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    isDraggingRef.current = true;
    previousMousePositionRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDraggingRef.current) return;
    const deltaX = e.clientX - previousMousePositionRef.current.x;
    const deltaY = e.clientY - previousMousePositionRef.current.y;

    rotationRef.current.y += deltaX * 0.005;
    rotationRef.current.x = Math.max(-1.2, Math.min(1.2, rotationRef.current.x + deltaY * 0.005));

    previousMousePositionRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const zoomDelta = e.deltaY * -0.001;
    zoomRef.current = Math.max(0.6, Math.min(2.0, zoomRef.current + zoomDelta));
  };

  return (
    <div className="relative w-full h-[600px] bg-slate-950 rounded-xl border border-slate-800 overflow-hidden shadow-2xl flex flex-col items-center justify-center">
      {/* 3D Canvas */}
      <canvas
        ref={canvasRef}
        width={900}
        height={600}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        className="cursor-grab active:cursor-grabbing w-full h-full object-contain"
      />

      {/* Floating HUD Header Controls */}
      <div className="absolute top-4 left-4 right-4 flex items-center justify-between pointer-events-none">
        <div className="flex items-center gap-3 bg-slate-900/80 backdrop-blur-md px-4 py-2 rounded-lg border border-cyan-500/30 pointer-events-auto">
          <GlobeIcon className="w-5 h-5 text-cyan-400 animate-spin" style={{ animationDuration: '10s' }} />
          <div>
            <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              Interactive 3D Weather Globe
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-mono">WebGL</span>
            </h3>
            <p className="text-xs text-slate-400">Drag to rotate • Scroll to zoom • Interactive anomaly projection</p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 bg-slate-900/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-700 pointer-events-auto">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-cyan-400 transition"
            title={isPlaying ? 'Pause Auto-Rotation' : 'Play Auto-Rotation'}
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          </button>
          <button
            onClick={() => { rotationRef.current = { x: 0.3, y: -0.8 }; zoomRef.current = 1.0; }}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-cyan-400 transition"
            title="Reset View"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <div className="h-4 w-px bg-slate-700 mx-1" />
          <button
            onClick={() => setShowGrid(!showGrid)}
            className={`px-2 py-1 text-xs rounded border transition ${showGrid ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' : 'text-slate-400 border-slate-700'}`}
          >
            Grid
          </button>
          <button
            onClick={() => setShowHeatmap(!showHeatmap)}
            className={`px-2 py-1 text-xs rounded border transition ${showHeatmap ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' : 'text-slate-400 border-slate-700'}`}
          >
            Heatmap
          </button>
        </div>
      </div>

      {/* Bottom Status Bar */}
      <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between pointer-events-none text-xs text-slate-400 bg-slate-900/60 backdrop-blur-sm px-4 py-2 rounded-lg border border-slate-800">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />
            Severe Events: {demoEvents.filter(e => e.severity === 'SEVERE').length}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            Moderate: {demoEvents.filter(e => e.severity === 'MODERATE').length}
          </span>
        </div>
        <div className="font-mono text-cyan-400">
          Domain: Bay of Bengal & Indian Ocean (68°E - 98°E, 5°N - 30°N)
        </div>
      </div>
    </div>
  );
};
