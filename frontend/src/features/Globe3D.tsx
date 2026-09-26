import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  Globe as GlobeIcon,
  Maximize2,
  Minimize2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  X,
  Sun,
  Moon,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { feature as topojsonFeature } from 'topojson-client';
import type { Topology } from 'topojson-specification';
import worldLand from 'world-atlas/land-110m.json';

import { useGeoJson } from '@/hooks/useGeoJson';
import { useEvents, useForecast } from '@/hooks/queries';
import { currentLead, useTimeline } from '@/stores/timeline';
import { useUi } from '@/stores/ui';
import { formatUtc, formatIst, leadLabel } from '@/lib/time';

export interface GlobeEvent {
  id: string;
  displayId?: string;
  type: string;
  severity: 'SEVERE' | 'MODERATE' | 'LOW';
  lat: number;
  lon: number;
  confidence?: string;
  intensity?: string;
  efi?: string;
  status?: string;
  probability?: number;
  attributes?: Record<string, unknown>;
}

interface Globe3DProps {
  events?: GlobeEvent[];
  selectedEventId?: string | null;
  onSelectEvent?: (event: GlobeEvent | null) => void;
  indiaFocusTrigger?: number;
}

const DEFAULT_EVENTS: GlobeEvent[] = [
  {
    id: 'EVT-001',
    type: 'CYCLONIC_STORM',
    severity: 'SEVERE',
    lat: 18.5,
    lon: 86.2,
    confidence: '94%',
    intensity: '222 mm/6h',
    efi: '+2.85',
    status: 'ACTIVE_TRACKING',
    probability: 0.94,
  },
  {
    id: 'EVT-002',
    type: 'HEAVY_PRECIPITATION',
    severity: 'MODERATE',
    lat: 14.2,
    lon: 82.5,
    confidence: '82%',
    intensity: '118 mm/6h',
    efi: '+1.64',
    status: 'OBSERVED',
    probability: 0.82,
  },
  {
    id: 'EVT-003',
    type: 'HIGH_WIND_ANOMALY',
    severity: 'SEVERE',
    lat: 21.8,
    lon: 88.5,
    confidence: '91%',
    intensity: '46.2 m/s',
    efi: '+2.41',
    status: 'ACTIVE_TRACKING',
    probability: 0.91,
  },
  {
    id: 'EVT-004',
    type: 'SQUALL_CLUSTER',
    severity: 'MODERATE',
    lat: 16.8,
    lon: 72.1,
    confidence: '78%',
    intensity: '88 mm/6h',
    efi: '+1.35',
    status: 'FORECAST_LEAD',
    probability: 0.78,
  },
];

interface HitBox {
  x: number;
  y: number;
  w: number;
  h: number;
  event: GlobeEvent;
}

export const Globe3D: React.FC<Globe3DProps> = ({
  events: propEvents,
  selectedEventId: controlledSelectedId,
  onSelectEvent,
  indiaFocusTrigger,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Layer toggles
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [showGrid, setShowGrid] = useState<boolean>(true);
  const [showAnomaly, setShowAnomaly] = useState<boolean>(true);
  const [showEvents, setShowEvents] = useState<boolean>(true);
  const [cameraMode, setCameraMode] = useState<'global' | 'india'>('global');
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // Selected event state
  const [internalSelectedEvent, setInternalSelectedEvent] = useState<GlobeEvent | null>(null);

  // Scientific Theme: Light vs Dark mode (defaults to Light mode as requested)
  const appTheme = useUi((s) => s.theme);
  const setAppTheme = useUi((s) => s.setTheme);
  const [localTheme, setLocalTheme] = useState<'light' | 'dark'>('light');
  const isLight = localTheme === 'light';

  useEffect(() => {
    setLocalTheme(appTheme);
  }, [appTheme]);

  // Sync app theme to light on initial mount
  useEffect(() => {
    if (appTheme !== 'light') {
      setAppTheme('light');
    }
  }, []);

  const toggleTheme = useCallback(() => {
    const next = isLight ? 'dark' : 'light';
    setLocalTheme(next);
    setAppTheme(next);
  }, [isLight, setAppTheme]);

  // Timeline and forecast queries
  const forecastQuery = useForecast();
  const eventsQuery = useEvents();
  const soiGeo = useGeoJson('india_soi_boundary.geojson');
  const statesGeo = useGeoJson<{ name: string; code?: string }>('india_states_full.geojson');

  const {
    leads: timelineLeads,
    index: timelineIndex,
    playing: timelinePlaying,
    setLead,
    setLeads,
    step: stepTimeline,
    toggle: toggleTimeline,
    pause: pauseTimeline,
  } = useTimeline();

  const curLead = useTimeline(currentLead);

  // Sync leads from forecast if available
  useEffect(() => {
    if (forecastQuery.data?.lead_hours && forecastQuery.data.lead_hours.length > 0) {
      setLeads(forecastQuery.data.lead_hours);
    } else if (timelineLeads.length === 0) {
      setLeads([0, 6, 12, 18, 24, 30, 36, 42, 48, 60, 72, 96, 120]);
    }
  }, [forecastQuery.data?.lead_hours, setLeads, timelineLeads.length]);

  // Combine query events or prop events or fallback
  const activeEvents: GlobeEvent[] = useMemo(() => {
    if (propEvents && propEvents.length > 0) return propEvents;
    if (eventsQuery.data && eventsQuery.data.length > 0) {
      return eventsQuery.data.map((e, idx) => {
        const val = typeof e.peak_intensity.value === 'number' ? Math.round(e.peak_intensity.value) : e.peak_intensity.value;
        const shortId = e.id.length > 12 ? `EVT-${String(idx + 1).padStart(3, '0')}` : e.id;
        return {
          id: e.id,
          displayId: shortId,
          type: e.event_type,
          severity: e.severity,
          lat: e.centroid.lat,
          lon: e.centroid.lon,
          confidence: e.confidence === 'HIGH' ? '92%' : e.confidence === 'MEDIUM' ? '76%' : '58%',
          intensity: `${val} ${e.peak_intensity.unit}`,
          efi: e.severity === 'SEVERE' ? '+2.45' : e.severity === 'MODERATE' ? '+1.65' : '+0.85',
          status: e.status,
          probability: e.probability,
        };
      });
    }
    return DEFAULT_EVENTS;
  }, [propEvents, eventsQuery.data]);

  const selectedEvent = useMemo(() => {
    if (controlledSelectedId !== undefined) {
      return activeEvents.find((e) => e.id === controlledSelectedId) || null;
    }
    return internalSelectedEvent;
  }, [controlledSelectedId, internalSelectedEvent, activeEvents]);

  const setSelected = useCallback(
    (evt: GlobeEvent | null) => {
      setInternalSelectedEvent(evt);
      if (onSelectEvent) onSelectEvent(evt);
    },
    [onSelectEvent]
  );

  // Helper to extract rings from GeoJSON features
  const extractRings = (features?: Array<{ geometry: { type: string; coordinates: any } }>) => {
    if (!features) return [];
    const rings: Array<Array<[number, number]>> = [];
    for (const f of features) {
      if (!f.geometry) continue;
      if (f.geometry.type === 'Polygon') {
        for (const r of (f.geometry as any).coordinates) {
          rings.push(r as Array<[number, number]>);
        }
      } else if (f.geometry.type === 'MultiPolygon') {
        for (const poly of (f.geometry as any).coordinates) {
          for (const r of poly) {
            rings.push(r as Array<[number, number]>);
          }
        }
      }
    }
    return rings;
  };

  // Extract World Land Rings
  const worldLandRings = useMemo(() => {
    try {
      const geo = topojsonFeature(worldLand as unknown as Topology, 'land') as unknown as {
        features: Array<{ geometry: { type: string; coordinates: any } }>;
      };
      return extractRings(geo?.features);
    } catch {
      return [];
    }
  }, []);

  // Extract Official Survey of India National Outer Boundary
  const indiaSoiRings = useMemo(() => extractRings(soiGeo.data?.features as any), [soiGeo.data]);

  // Extract All 35 Indian States and UTs Boundaries
  const indiaStateRings = useMemo(() => extractRings(statesGeo.data?.features as any), [statesGeo.data]);

  // Orbit / Camera state
  const centerLatRef = useRef<number>(18.0);
  const centerLonRef = useRef<number>(75.0);
  const zoomRef = useRef<number>(1.05);

  // Target camera for smooth animated transitions
  const targetCamRef = useRef<{ lat: number; lon: number; zoom: number } | null>(null);

  // Mouse interaction state
  const isDraggingRef = useRef<boolean>(false);
  const lastMousePosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const hitboxesRef = useRef<HitBox[]>([]);

  // Function to smoothly transition camera
  const animateCameraTo = useCallback((lat: number, lon: number, zoom: number) => {
    targetCamRef.current = { lat, lon, zoom };
  }, []);

  // Switch camera modes
  const handleSetCameraMode = useCallback(
    (mode: 'global' | 'india') => {
      setCameraMode(mode);
      if (mode === 'india') {
        // Center on India domain: 22° N, 82° E with 1.45x zoom
        animateCameraTo(22.0, 82.0, 1.45);
      } else {
        // Global perspective: 15° N, 65° E with 1.0x zoom
        animateCameraTo(15.0, 65.0, 1.0);
      }
    },
    [animateCameraTo]
  );

  // Trigger India focus from external prop if provided
  useEffect(() => {
    if (indiaFocusTrigger && indiaFocusTrigger > 0) {
      handleSetCameraMode('india');
    }
  }, [indiaFocusTrigger, handleSetCameraMode]);

  // Handle View Reset
  const handleResetView = useCallback(() => {
    if (cameraMode === 'india') {
      animateCameraTo(22.0, 82.0, 1.45);
    } else {
      animateCameraTo(15.0, 65.0, 1.0);
    }
  }, [cameraMode, animateCameraTo]);

  // Center camera on specific event coordinates
  const centerOnEvent = useCallback(
    (lat: number, lon: number) => {
      animateCameraTo(lat, lon, 1.55);
    },
    [animateCameraTo]
  );

  // Fullscreen toggle
  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  useEffect(() => {
    const handleFsChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFsChange);
    return () => document.removeEventListener('fullscreenchange', handleFsChange);
  }, []);

  // Main Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let animTime = 0;

    const render = () => {
      animTime += 0.025;

      // Handle smooth camera interpolation
      if (targetCamRef.current) {
        const t = targetCamRef.current;
        const lerpFactor = 0.08;
        centerLatRef.current += (t.lat - centerLatRef.current) * lerpFactor;

        // Longitude wrapping delta for shortest rotation path
        let dLon = ((t.lon - centerLonRef.current + 540) % 360) - 180;
        centerLonRef.current += dLon * lerpFactor;
        zoomRef.current += (t.zoom - zoomRef.current) * lerpFactor;

        if (
          Math.abs(t.lat - centerLatRef.current) < 0.1 &&
          Math.abs(dLon) < 0.1 &&
          Math.abs(t.zoom - zoomRef.current) < 0.01
        ) {
          centerLatRef.current = t.lat;
          centerLonRef.current = t.lon;
          zoomRef.current = t.zoom;
          targetCamRef.current = null;
        }
      } else if (isPlaying && !isDraggingRef.current && cameraMode === 'global') {
        // Gentle constant eastward auto-rotation
        centerLonRef.current = (centerLonRef.current + 0.12) % 360;
      }

      const width = canvas.width;
      const height = canvas.height;
      // Prominent Earth sizing: 65% to 70% of viewport
      const radius = Math.min(width, height) * 0.36 * zoomRef.current;
      const centerX = width / 2;
      const centerY = height / 2;

      // Clear Canvas
      ctx.clearRect(0, 0, width, height);
      hitboxesRef.current = [];

      // 1. Background (Light scientific laboratory vs deep space)
      if (isLight) {
        ctx.fillStyle = '#f8fafc';
        ctx.fillRect(0, 0, width, height);

        // Faint scientific coordinate grid dots
        ctx.fillStyle = 'rgba(71, 85, 105, 0.16)';
        for (let i = 0; i < 75; i++) {
          const sx = ((Math.sin(i * 127 + 1) * 0.5 + 0.5) * width);
          const sy = ((Math.cos(i * 91 + 3) * 0.5 + 0.5) * height);
          const sSize = i % 4 === 0 ? 1.4 : 0.8;
          ctx.beginPath();
          ctx.arc(sx, sy, sSize, 0, Math.PI * 2);
          ctx.fill();
        }
      } else {
        ctx.fillStyle = '#030816';
        ctx.fillRect(0, 0, width, height);

        // Subtle scientific starry grid dots
        ctx.fillStyle = 'rgba(255, 255, 255, 0.22)';
        for (let i = 0; i < 75; i++) {
          const sx = ((Math.sin(i * 127 + 1) * 0.5 + 0.5) * width);
          const sy = ((Math.cos(i * 91 + 3) * 0.5 + 0.5) * height);
          const sSize = i % 4 === 0 ? 1.4 : 0.8;
          ctx.beginPath();
          ctx.arc(sx, sy, sSize, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // 2. Atmospheric Outer Glow
      const glowGrad = ctx.createRadialGradient(
        centerX,
        centerY,
        radius * 0.96,
        centerX,
        centerY,
        radius * 1.2
      );
      if (isLight) {
        glowGrad.addColorStop(0, 'rgba(14, 165, 233, 0.26)');
        glowGrad.addColorStop(0.45, 'rgba(56, 189, 248, 0.10)');
        glowGrad.addColorStop(1, 'rgba(248, 250, 252, 0)');
      } else {
        glowGrad.addColorStop(0, 'rgba(14, 165, 233, 0.32)');
        glowGrad.addColorStop(0.45, 'rgba(56, 189, 248, 0.12)');
        glowGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
      }
      ctx.fillStyle = glowGrad;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius * 1.2, 0, Math.PI * 2);
      ctx.fill();

      // 3. Ocean Sphere Base (Pale scientific ocean vs deep navy)
      const oceanGrad = ctx.createRadialGradient(
        centerX - radius * 0.3,
        centerY - radius * 0.35,
        radius * 0.05,
        centerX,
        centerY,
        radius
      );
      if (isLight) {
        oceanGrad.addColorStop(0, '#e0f2fe');   // sky-100 highlight
        oceanGrad.addColorStop(0.55, '#bae6fd'); // sky-200
        oceanGrad.addColorStop(0.85, '#7dd3fc'); // sky-300
        oceanGrad.addColorStop(1, '#38bdf8');   // sky-400 limb
      } else {
        oceanGrad.addColorStop(0, '#0f294a');
        oceanGrad.addColorStop(0.65, '#07162c');
        oceanGrad.addColorStop(1, '#020914');
      }

      ctx.save();
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.fillStyle = oceanGrad;
      ctx.fill();
      ctx.clip(); // Clip all land and anomalies inside sphere

      // 4. Standard Orthographic Projection Math
      const curLatCenter = centerLatRef.current;
      const curLonCenter = centerLonRef.current;
      const phi0 = (curLatCenter * Math.PI) / 180;

      const project3D = (lat: number, lon: number) => {
        const phi = (lat * Math.PI) / 180;
        let dLon = ((lon - curLonCenter + 540) % 360) - 180;
        const dLam = (dLon * Math.PI) / 180;

        const cosPhi = Math.cos(phi);
        const sinPhi = Math.sin(phi);
        const cosPhi0 = Math.cos(phi0);
        const sinPhi0 = Math.sin(phi0);
        const cosDLam = Math.cos(dLam);
        const sinDLam = Math.sin(dLam);

        const x = cosPhi * sinDLam;
        const y = cosPhi0 * sinPhi - sinPhi0 * cosPhi * cosDLam;
        const z = sinPhi0 * sinPhi + cosPhi0 * cosPhi * cosDLam;

        const screenX = centerX + x * radius;
        const screenY = centerY - y * radius;
        const visible = z > -0.05;

        return { x: screenX, y: screenY, z, visible };
      };

      // 5. Graticule Lat/Lon Coordinate Grid
      if (showGrid) {
        ctx.strokeStyle = isLight ? 'rgba(15, 23, 42, 0.12)' : 'rgba(56, 189, 248, 0.14)';
        ctx.lineWidth = 0.9;

        // Latitude circles (-60° to +60°)
        for (let lat = -60; lat <= 60; lat += 20) {
          ctx.beginPath();
          let started = false;
          for (let lon = -180; lon <= 180; lon += 4) {
            const p = project3D(lat, lon);
            if (p.visible) {
              if (!started) {
                ctx.moveTo(p.x, p.y);
                started = true;
              } else {
                ctx.lineTo(p.x, p.y);
              }
            } else {
              started = false;
            }
          }
          ctx.stroke();
        }

        // Longitude meridians (-180° to +180°)
        for (let lon = -180; lon < 180; lon += 30) {
          ctx.beginPath();
          let started = false;
          for (let lat = -80; lat <= 80; lat += 4) {
            const p = project3D(lat, lon);
            if (p.visible) {
              if (!started) {
                ctx.moveTo(p.x, p.y);
                started = true;
              } else {
                ctx.lineTo(p.x, p.y);
              }
            } else {
              started = false;
            }
          }
          ctx.stroke();
        }
      }

      // 6. World Continent Coastlines (Real TopoJSON Boundaries)
      if (worldLandRings.length > 0) {
        ctx.strokeStyle = isLight ? 'rgba(71, 85, 105, 0.42)' : 'rgba(56, 189, 248, 0.32)';
        ctx.fillStyle = isLight ? 'rgba(241, 245, 249, 0.88)' : 'rgba(14, 38, 70, 0.45)';
        ctx.lineWidth = isLight ? 1.0 : 1.1;

        for (const ring of worldLandRings) {
          ctx.beginPath();
          let started = false;
          for (let i = 0; i < ring.length; i += 2) {
            const pt = ring[i];
            if (!pt) continue;
            const p = project3D(pt[1], pt[0]);
            if (p.visible) {
              if (!started) {
                ctx.moveTo(p.x, p.y);
                started = true;
              } else {
                ctx.lineTo(p.x, p.y);
              }
            } else {
              started = false;
            }
          }
          ctx.stroke();
        }
      }

      // 7a. Internal State Boundaries (All 35 Indian States & UTs)
      if (indiaStateRings.length > 0) {
        ctx.strokeStyle = isLight ? 'rgba(2, 132, 199, 0.55)' : 'rgba(56, 189, 248, 0.40)';
        ctx.lineWidth = 1.0;

        for (const ring of indiaStateRings) {
          ctx.beginPath();
          let started = false;
          for (let i = 0; i < ring.length; i += 2) {
            const pt = ring[i];
            if (!pt) continue;
            const p = project3D(pt[1], pt[0]);
            if (p.visible) {
              if (!started) {
                ctx.moveTo(p.x, p.y);
                started = true;
              } else {
                ctx.lineTo(p.x, p.y);
              }
            } else {
              started = false;
            }
          }
          ctx.stroke();
        }
      }

      // 7b. Official Complete Survey of India National Outer Boundary (37.10°N down to 6.75°N)
      if (indiaSoiRings.length > 0) {
        ctx.strokeStyle = isLight ? 'rgba(3, 105, 161, 0.95)' : 'rgba(56, 189, 248, 0.95)';
        ctx.lineWidth = 1.8;

        for (const ring of indiaSoiRings) {
          ctx.beginPath();
          let started = false;
          for (let i = 0; i < ring.length; i += 2) {
            const pt = ring[i];
            if (!pt) continue;
            const p = project3D(pt[1], pt[0]);
            if (p.visible) {
              if (!started) {
                ctx.moveTo(p.x, p.y);
                started = true;
              } else {
                ctx.lineTo(p.x, p.y);
              }
            } else {
              started = false;
            }
          }
          ctx.stroke();
        }
      }

      // 8. Meteorological Weather Anomaly Field (Restrained Scientific Palettes)
      if (showAnomaly) {
        const anomalyCenters = [
          { lat: 18.2, lon: 86.8, maxEfi: 2.85, rKm: 320, isSevere: true },
          { lat: 21.6, lon: 88.2, maxEfi: 2.35, rKm: 260, isSevere: true },
          { lat: 14.5, lon: 82.8, maxEfi: 1.65, rKm: 240, isSevere: false },
          { lat: 16.5, lon: 71.8, maxEfi: 1.40, rKm: 200, isSevere: false },
          { lat: 25.5, lon: 85.0, maxEfi: 1.25, rKm: 180, isSevere: false },
        ];

        for (const ac of anomalyCenters) {
          const p = project3D(ac.lat, ac.lon);
          if (p.visible && p.z > 0.1) {
            // Anomaly gradient lobe
            const lobeRadius = (ac.rKm / 12) * zoomRef.current + Math.sin(animTime * 2 + ac.lat) * 2;
            const hGrad = ctx.createRadialGradient(p.x, p.y, 2, p.x, p.y, lobeRadius);

            if (ac.isSevere) {
              if (isLight) {
                hGrad.addColorStop(0, 'rgba(220, 38, 38, 0.70)'); // Severe Red
                hGrad.addColorStop(0.35, 'rgba(234, 88, 12, 0.50)'); // High Orange
                hGrad.addColorStop(0.7, 'rgba(217, 119, 6, 0.28)'); // Moderate Yellow
                hGrad.addColorStop(1, 'rgba(239, 68, 68, 0)');
              } else {
                hGrad.addColorStop(0, 'rgba(239, 68, 68, 0.65)'); // Severe Red
                hGrad.addColorStop(0.35, 'rgba(249, 115, 22, 0.45)'); // High Orange
                hGrad.addColorStop(0.7, 'rgba(234, 179, 8, 0.25)'); // Moderate Yellow
                hGrad.addColorStop(1, 'rgba(14, 165, 233, 0)');
              }
            } else {
              if (isLight) {
                hGrad.addColorStop(0, 'rgba(217, 119, 6, 0.62)'); // Moderate Amber
                hGrad.addColorStop(0.5, 'rgba(2, 132, 199, 0.35)'); // Blue
                hGrad.addColorStop(1, 'rgba(14, 165, 233, 0)');
              } else {
                hGrad.addColorStop(0, 'rgba(234, 179, 8, 0.55)'); // Moderate Amber
                hGrad.addColorStop(0.5, 'rgba(56, 189, 248, 0.30)'); // Cyan
                hGrad.addColorStop(1, 'rgba(14, 165, 233, 0)');
              }
            }

            ctx.fillStyle = hGrad;
            ctx.beginPath();
            ctx.arc(p.x, p.y, lobeRadius, 0, Math.PI * 2);
            ctx.fill();

            // Fine contour ring
            ctx.strokeStyle = ac.isSevere
              ? isLight
                ? 'rgba(220, 38, 38, 0.45)'
                : 'rgba(239, 68, 68, 0.4)'
              : isLight
              ? 'rgba(217, 119, 6, 0.40)'
              : 'rgba(234, 179, 8, 0.35)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(p.x, p.y, lobeRadius * 0.65, 0, Math.PI * 2);
            ctx.stroke();
          }
        }
      }

      // 9. 3D Event Pulse Markers & Intelligent Collision-Avoidance Badges
      if (showEvents) {
        // Collect visible events with projected 2D coordinates
        const visibleEvents: Array<{
          evt: GlobeEvent;
          p: { x: number; y: number; z: number };
          isSevere: boolean;
          isSelected: boolean;
        }> = [];

        activeEvents.forEach((evt) => {
          const p = project3D(evt.lat, evt.lon);
          if (p.visible && p.z > 0.05) {
            visibleEvents.push({
              evt,
              p,
              isSevere: evt.severity === 'SEVERE',
              isSelected: selectedEvent?.id === evt.id,
            });
          }
        });

        // Sort by Y position for clean top-to-bottom label placement
        visibleEvents.sort((a, b) => a.p.y - b.p.y);

        // Pre-allocate slots to avoid label overlaps
        const placedBadges: Array<{ x: number; y: number; w: number; h: number }> = [];

        visibleEvents.forEach((item, index) => {
          const { evt, p, isSevere, isSelected } = item;
          const color = isSevere ? '#ef4444' : evt.severity === 'MODERATE' ? '#f59e0b' : '#38bdf8';

          // 9a. Ground surface pulsing radar ring
          const ringRad = ((animTime * 14 + index * 6) % 22) + 4;
          const ringAlpha = Math.max(0, 1 - ringRad / 26);
          ctx.strokeStyle = isSevere
            ? `rgba(239, 68, 68, ${ringAlpha})`
            : `rgba(245, 158, 11, ${ringAlpha})`;
          ctx.lineWidth = 1.6;
          ctx.beginPath();
          ctx.arc(p.x, p.y, ringRad, 0, Math.PI * 2);
          ctx.stroke();

          // Ground central anchor dot
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(p.x, p.y, isSelected ? 5.5 : 4, 0, Math.PI * 2);
          ctx.fill();

          // 9b. Non-overlapping Leader Line and Badge Placement
          const badgeW = 126;
          const badgeH = 34;

          // Test candidate quadrant offsets
          const offsets = [
            { dx: 38, dy: -32 },
            { dx: 38, dy: 24 },
            { dx: -badgeW - 38, dy: -32 },
            { dx: -badgeW - 38, dy: 24 },
          ];

          // Alternate preferred offset by index
          const preferredOffset = offsets[index % offsets.length] || offsets[0]!;
          let badgeX = p.x + preferredOffset.dx;
          let badgeY = p.y + preferredOffset.dy;

          // Check collisions against previously placed badges
          let hasOverlap = true;
          let attempts = 0;
          while (hasOverlap && attempts < 8) {
            hasOverlap = placedBadges.some(
              (b) =>
                badgeX < b.x + b.w + 6 &&
                badgeX + badgeW + 6 > b.x &&
                badgeY < b.y + b.h + 6 &&
                badgeY + badgeH + 6 > b.y
            );
            if (hasOverlap) {
              // Stagger vertically
              badgeY += index % 2 === 0 ? 38 : -38;
              attempts++;
            }
          }

          // Clamp badge inside canvas
          badgeX = Math.max(12, Math.min(width - badgeW - 12, badgeX));
          badgeY = Math.max(50, Math.min(height - badgeH - 50, badgeY));

          placedBadges.push({ x: badgeX, y: badgeY, w: badgeW, h: badgeH });

          // Leader line with elbow joint
          ctx.strokeStyle = isSelected
            ? color
            : isLight
            ? 'rgba(71, 85, 105, 0.75)'
            : 'rgba(148, 163, 184, 0.7)';
          ctx.lineWidth = isSelected ? 1.8 : 1.1;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          const elbowX = badgeX > p.x ? badgeX : badgeX + badgeW;
          const elbowY = badgeY + badgeH / 2;
          ctx.lineTo((p.x + elbowX) / 2, elbowY);
          ctx.lineTo(elbowX, elbowY);
          ctx.stroke();

          // 9c. Draw Badge Card
          ctx.fillStyle = isLight
            ? isSelected
              ? 'rgba(255, 255, 255, 0.98)'
              : 'rgba(255, 255, 255, 0.94)'
            : isSelected
            ? 'rgba(15, 23, 42, 0.95)'
            : 'rgba(8, 14, 28, 0.9)';
          ctx.beginPath();
          ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 6);
          ctx.fill();

          ctx.strokeStyle = isSelected
            ? color
            : isSevere
            ? isLight
              ? 'rgba(220, 38, 38, 0.8)'
              : 'rgba(239, 68, 68, 0.7)'
            : isLight
            ? 'rgba(217, 119, 6, 0.7)'
            : 'rgba(245, 158, 11, 0.6)';
          ctx.lineWidth = isSelected ? 1.8 : 1.1;
          ctx.stroke();

          // Badge Content - Row 1: Status Dot + ID + Severity
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(badgeX + 10, badgeY + 12, 3.5, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = isLight ? '#0f172a' : '#f8fafc';
          ctx.font = 'bold 10px JetBrains Mono, monospace';
          const labelId = evt.displayId || (evt.id.length > 12 ? `EVT-${evt.id.slice(0, 6).toUpperCase()}` : evt.id);
          ctx.fillText(labelId, badgeX + 20, badgeY + 15);

          ctx.fillStyle = isSevere
            ? isLight
              ? '#b91c1c'
              : '#fca5a5'
            : isLight
            ? '#b45309'
            : '#fde68a';
          ctx.font = 'bold 8.5px Inter, sans-serif';
          ctx.fillText(evt.severity, badgeX + 78, badgeY + 15);

          // Badge Content - Row 2: Metric + EFI
          ctx.fillStyle = isLight ? '#475569' : '#94a3b8';
          ctx.font = '9px JetBrains Mono, monospace';
          const subText = `${evt.intensity || 'Active'} • EFI ${evt.efi || '+2.0'}`;
          ctx.fillText(subText, badgeX + 10, badgeY + 28);

          // Register HitBox for interaction
          hitboxesRef.current.push({
            x: badgeX,
            y: badgeY,
            w: badgeW,
            h: badgeH,
            event: evt,
          });

          // Also register ground point hitbox
          hitboxesRef.current.push({
            x: p.x - 14,
            y: p.y - 14,
            w: 28,
            h: 28,
            event: evt,
          });
        });
      }

      ctx.restore(); // End ocean sphere clipping

      // 10. Specular Shading / Hemisphere Illumination Rim
      const specGrad = ctx.createRadialGradient(
        centerX - radius * 0.45,
        centerY - radius * 0.45,
        0,
        centerX,
        centerY,
        radius
      );
      if (isLight) {
        specGrad.addColorStop(0, 'rgba(255, 255, 255, 0.45)');
        specGrad.addColorStop(0.4, 'rgba(255, 255, 255, 0.05)');
        specGrad.addColorStop(0.85, 'rgba(15, 23, 42, 0.08)');
        specGrad.addColorStop(1, 'rgba(15, 23, 42, 0.28)');
      } else {
        specGrad.addColorStop(0, 'rgba(255, 255, 255, 0.12)');
        specGrad.addColorStop(0.4, 'rgba(255, 255, 255, 0.02)');
        specGrad.addColorStop(0.85, 'rgba(0, 0, 0, 0.25)');
        specGrad.addColorStop(1, 'rgba(0, 0, 0, 0.65)');
      }
      ctx.fillStyle = specGrad;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.fill();

      // Sharp subtle outer rim
      ctx.strokeStyle = isLight ? 'rgba(3, 105, 161, 0.45)' : 'rgba(56, 189, 248, 0.55)';
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.stroke();

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [
    isPlaying,
    showGrid,
    showAnomaly,
    showEvents,
    cameraMode,
    isLight,
    activeEvents,
    selectedEvent,
    worldLandRings,
    indiaSoiRings,
    indiaStateRings,
  ]);

  // Mouse & Drag Orbit Controls
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    isDraggingRef.current = true;
    lastMousePosRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Check hitboxes for pointer cursor
    const rect = canvas.getBoundingClientRect();
    const mouseX = ((e.clientX - rect.left) / rect.width) * canvas.width;
    const mouseY = ((e.clientY - rect.top) / rect.height) * canvas.height;

    const isHoveringHitbox = hitboxesRef.current.some(
      (hb) =>
        mouseX >= hb.x &&
        mouseX <= hb.x + hb.w &&
        mouseY >= hb.y &&
        mouseY <= hb.y + hb.h
    );

    if (isHoveringHitbox) {
      canvas.style.cursor = 'pointer';
    } else {
      canvas.style.cursor = isDraggingRef.current ? 'grabbing' : 'grab';
    }

    if (!isDraggingRef.current) return;

    const deltaX = e.clientX - lastMousePosRef.current.x;
    const deltaY = e.clientY - lastMousePosRef.current.y;

    // Standard orthographic camera rotation
    centerLonRef.current = (centerLonRef.current - deltaX * 0.35 + 360) % 360;
    centerLatRef.current = Math.max(-80, Math.min(80, centerLatRef.current + deltaY * 0.35));

    lastMousePosRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const clickX = ((e.clientX - rect.left) / rect.width) * canvas.width;
    const clickY = ((e.clientY - rect.top) / rect.height) * canvas.height;

    // Check if clicked inside any event hitbox
    const clickedBox = hitboxesRef.current.find(
      (hb) =>
        clickX >= hb.x &&
        clickX <= hb.x + hb.w &&
        clickY >= hb.y &&
        clickY <= hb.y + hb.h
    );

    if (clickedBox) {
      setSelected(clickedBox.event);
    }
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const delta = e.deltaY * -0.0012;
    zoomRef.current = Math.max(0.75, Math.min(2.4, zoomRef.current + delta));
  };

  // Forecast Timeline details
  const validTimes = forecastQuery.data?.valid_times || [];
  const currentValidTime = validTimes[timelineIndex] || '2026-09-26T12:00:00Z';

  return (
    <div
      ref={containerRef}
      className={`relative w-full rounded-2xl border transition-colors duration-300 overflow-hidden flex flex-col ${
        isLight
          ? 'border-slate-200 bg-slate-50 text-slate-800 shadow-xl'
          : 'border-slate-800 bg-[#020713] text-slate-200 shadow-2xl'
      } ${isFullscreen ? 'h-screen' : 'h-[640px]'}`}
    >
      {/* 3D Canvas */}
      <div className="relative flex-1 w-full h-full overflow-hidden">
        <canvas
          ref={canvasRef}
          width={1200}
          height={750}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onClick={handleCanvasClick}
          onWheel={handleWheel}
          className="w-full h-full object-cover select-none"
        />

        {/* TOP-LEFT: Compact Info Overlay */}
        <div className="absolute top-4 left-4 z-10 pointer-events-auto">
          <div
            className={`backdrop-blur-md px-3.5 py-2.5 rounded-xl border shadow-xl flex items-center gap-3 transition-colors ${
              isLight
                ? 'bg-white/95 border-slate-200 text-slate-800 shadow-md'
                : 'bg-slate-950/85 border-slate-800 text-slate-100 shadow-xl'
            }`}
          >
            <div
              className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 ${
                isLight
                  ? 'bg-sky-50 border-sky-200 text-sky-600'
                  : 'bg-cyan-950 border-cyan-700/60 text-cyan-400'
              }`}
            >
              <GlobeIcon className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold uppercase tracking-wider">
                  GLOBAL ANOMALY FIELD
                </span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-bold border ${
                    isLight
                      ? 'bg-sky-100 text-sky-800 border-sky-300'
                      : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30'
                  }`}
                >
                  REANALYSIS
                </span>
              </div>
              <p
                className={`text-[11px] mt-0.5 font-mono ${
                  isLight ? 'text-slate-500' : 'text-slate-400'
                }`}
              >
                Drag to rotate • Scroll to zoom • Click markers to inspect
              </p>
            </div>
          </div>
        </div>

        {/* TOP-RIGHT: HUD Controls */}
        <div className="absolute top-4 right-4 z-10 flex flex-wrap items-center gap-2 pointer-events-auto">
          {/* Mode Switcher */}
          <div
            className={`flex backdrop-blur-md p-1 rounded-xl border shadow-xl transition-colors ${
              isLight
                ? 'bg-white/95 border-slate-200 shadow-md'
                : 'bg-slate-950/90 border-slate-800 shadow-xl'
            }`}
            role="group"
            aria-label="Camera Mode"
          >
            <button
              onClick={() => handleSetCameraMode('global')}
              className={`px-3 py-1.5 text-xs font-mono font-bold rounded-lg transition ${
                cameraMode === 'global'
                  ? 'bg-cyan-600 text-white shadow'
                  : isLight
                  ? 'text-slate-600 hover:text-slate-900'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Full Global Earth View"
              aria-pressed={cameraMode === 'global'}
            >
              GLOBAL
            </button>
            <button
              onClick={() => handleSetCameraMode('india')}
              className={`px-3 py-1.5 text-xs font-mono font-bold rounded-lg transition ${
                cameraMode === 'india'
                  ? 'bg-cyan-600 text-white shadow'
                  : isLight
                  ? 'text-slate-600 hover:text-slate-900'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Focus on India (Official Boundaries, J&K, Ladakh, Arunachal Pradesh)"
              aria-pressed={cameraMode === 'india'}
            >
              INDIA FOCUS
            </button>
          </div>

          {/* Action HUD buttons */}
          <div
            className={`flex items-center gap-1 backdrop-blur-md p-1 rounded-xl border shadow-xl transition-colors ${
              isLight
                ? 'bg-white/95 border-slate-200 text-slate-700 shadow-md'
                : 'bg-slate-950/90 border-slate-800 text-slate-200 shadow-xl'
            }`}
          >
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className={`p-2 rounded-lg transition ${
                isLight
                  ? 'hover:bg-slate-100 text-slate-600 hover:text-cyan-700'
                  : 'hover:bg-slate-800 text-slate-300 hover:text-cyan-400'
              }`}
              title={isPlaying ? 'Pause Auto-Rotation' : 'Resume Auto-Rotation'}
              aria-label={isPlaying ? 'Pause rotation' : 'Resume rotation'}
            >
              {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            </button>
            <button
              onClick={handleResetView}
              className={`p-2 rounded-lg transition ${
                isLight
                  ? 'hover:bg-slate-100 text-slate-600 hover:text-cyan-700'
                  : 'hover:bg-slate-800 text-slate-300 hover:text-cyan-400'
              }`}
              title="Reset Camera View"
              aria-label="Reset Camera View"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <div className={`h-4 w-px mx-1 ${isLight ? 'bg-slate-200' : 'bg-slate-800'}`} />
            <button
              onClick={() => setShowGrid(!showGrid)}
              className={`px-2.5 py-1 text-xs font-mono rounded-lg border transition ${
                showGrid
                  ? isLight
                    ? 'bg-sky-100 text-sky-800 border-sky-300 font-bold'
                    : 'bg-cyan-950/80 text-cyan-300 border-cyan-700/60 font-bold'
                  : isLight
                  ? 'text-slate-500 border-transparent hover:bg-slate-100'
                  : 'text-slate-400 border-transparent hover:bg-slate-800'
              }`}
              title="Toggle Coordinate Grid"
              aria-pressed={showGrid}
            >
              GRID
            </button>
            <button
              onClick={() => setShowAnomaly(!showAnomaly)}
              className={`px-2.5 py-1 text-xs font-mono rounded-lg border transition ${
                showAnomaly
                  ? isLight
                    ? 'bg-sky-100 text-sky-800 border-sky-300 font-bold'
                    : 'bg-cyan-950/80 text-cyan-300 border-cyan-700/60 font-bold'
                  : isLight
                  ? 'text-slate-500 border-transparent hover:bg-slate-100'
                  : 'text-slate-400 border-transparent hover:bg-slate-800'
              }`}
              title="Toggle Weather Anomaly Field"
              aria-pressed={showAnomaly}
            >
              ANOMALY
            </button>
            <button
              onClick={() => setShowEvents(!showEvents)}
              className={`px-2.5 py-1 text-xs font-mono rounded-lg border transition ${
                showEvents
                  ? isLight
                    ? 'bg-sky-100 text-sky-800 border-sky-300 font-bold'
                    : 'bg-cyan-950/80 text-cyan-300 border-cyan-700/60 font-bold'
                  : isLight
                  ? 'text-slate-500 border-transparent hover:bg-slate-100'
                  : 'text-slate-400 border-transparent hover:bg-slate-800'
              }`}
              title="Toggle Extreme Event Markers"
              aria-pressed={showEvents}
            >
              EVENTS
            </button>
            <div className={`h-4 w-px mx-1 ${isLight ? 'bg-slate-200' : 'bg-slate-800'}`} />
            {/* Theme Toggle Button */}
            <button
              onClick={toggleTheme}
              className={`p-2 rounded-lg transition ${
                isLight
                  ? 'hover:bg-slate-100 text-amber-600 hover:text-amber-700'
                  : 'hover:bg-slate-800 text-amber-400 hover:text-amber-300'
              }`}
              title={isLight ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
              aria-label={isLight ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
            >
              {isLight ? <Moon className="w-4 h-4 text-slate-700" /> : <Sun className="w-4 h-4 text-amber-400" />}
            </button>
            <button
              onClick={handleToggleFullscreen}
              className={`p-2 rounded-lg transition ${
                isLight
                  ? 'hover:bg-slate-100 text-slate-600 hover:text-cyan-700'
                  : 'hover:bg-slate-800 text-slate-300 hover:text-cyan-400'
              }`}
              title="Toggle Fullscreen"
              aria-label="Toggle Fullscreen"
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* BOTTOM-LEFT: Scientific Anomaly Legend */}
        <div className="absolute bottom-4 left-4 z-10 pointer-events-auto">
          <div
            className={`backdrop-blur-md p-3.5 rounded-xl border shadow-xl transition-colors ${
              isLight
                ? 'bg-white/95 border-slate-200 text-slate-800 shadow-md'
                : 'bg-slate-950/90 border-slate-800 text-slate-200 shadow-xl'
            }`}
          >
            <div className="text-[10px] font-bold font-mono tracking-wider uppercase mb-2 flex items-center justify-between gap-4">
              <span className={isLight ? 'text-slate-700' : 'text-slate-300'}>
                EXTREME ANOMALY INDEX (EFI)
              </span>
              <span className={isLight ? 'text-sky-600 font-normal' : 'text-cyan-400 font-normal'}>
                σ / Climatology
              </span>
            </div>
            <div
              className={`w-64 h-3.5 rounded-md overflow-hidden flex shadow-inner border ${
                isLight ? 'border-slate-300' : 'border-slate-700/70'
              }`}
            >
              <div className="flex-1 bg-sky-900" title="Normal: -2 to 0 σ" />
              <div className="flex-1 bg-cyan-500" title="Low Anomaly: 0 to +1 σ" />
              <div className="flex-1 bg-amber-400" title="Moderate: +1 to +2 σ" />
              <div className="flex-1 bg-orange-500" title="High: +2 to +2.5 σ" />
              <div className="flex-1 bg-red-600" title="Severe: > +2.5 σ" />
            </div>
            <div
              className={`flex justify-between text-[9px] font-mono mt-1.5 ${
                isLight ? 'text-slate-600' : 'text-slate-400'
              }`}
            >
              <span>-2 (Normal)</span>
              <span>0</span>
              <span>+1 (Mod)</span>
              <span>+2 (High)</span>
              <span>+3 (Severe)</span>
            </div>
          </div>
        </div>

        {/* FLOATING EVENT DETAILS CARD (when an event is selected) */}
        {selectedEvent && (
          <div
            className={`absolute top-20 left-4 z-20 w-80 rounded-2xl border p-4 shadow-2xl backdrop-blur-md animate-in fade-in zoom-in-95 duration-150 transition-colors ${
              isLight
                ? 'border-slate-200 bg-white/98 text-slate-800 shadow-xl'
                : 'border-slate-700/80 bg-slate-950/95 text-slate-100 shadow-2xl'
            }`}
          >
            <div className={`flex items-start justify-between border-b pb-2.5 ${isLight ? 'border-slate-200' : 'border-slate-800'}`}>
              <div>
                <div className="flex items-center gap-2">
                  <span className={`font-mono text-sm font-bold ${isLight ? 'text-sky-700' : 'text-cyan-400'}`}>
                    {selectedEvent.id}
                  </span>
                  <span
                    className={`px-2 py-0.5 text-[10px] font-bold font-mono rounded ${
                      selectedEvent.severity === 'SEVERE'
                        ? isLight
                          ? 'bg-red-50 text-red-700 border border-red-200'
                          : 'bg-red-500/20 text-red-300 border border-red-500/40'
                        : selectedEvent.severity === 'MODERATE'
                        ? isLight
                          ? 'bg-amber-50 text-amber-700 border border-amber-200'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                        : isLight
                        ? 'bg-sky-50 text-sky-700 border border-sky-200'
                        : 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
                    }`}
                  >
                    {selectedEvent.severity}
                  </span>
                </div>
                <h4 className={`text-xs font-semibold mt-1 uppercase tracking-wide ${isLight ? 'text-slate-600' : 'text-slate-300'}`}>
                  {selectedEvent.type.replace(/_/g, ' ')}
                </h4>
              </div>
              <button
                onClick={() => setSelected(null)}
                className={`p-1 rounded-lg transition ${
                  isLight
                    ? 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
                aria-label="Close event inspection"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className={`grid grid-cols-2 gap-2.5 py-3 text-xs border-b ${isLight ? 'border-slate-200' : 'border-slate-800'}`}>
              <div>
                <span className={`text-[10px] uppercase font-mono tracking-wider ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                  Severity
                </span>
                <div className={`font-semibold font-mono mt-0.5 flex items-center gap-1.5 ${isLight ? 'text-slate-800' : 'text-slate-200'}`}>
                  <span
                    className={`w-2 h-2 rounded-full ${
                      selectedEvent.severity === 'SEVERE'
                        ? 'bg-red-500'
                        : selectedEvent.severity === 'MODERATE'
                        ? 'bg-amber-500'
                        : 'bg-blue-500'
                    }`}
                  />
                  {selectedEvent.severity}
                </div>
              </div>
              <div>
                <span className={`text-[10px] uppercase font-mono tracking-wider ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                  Confidence
                </span>
                <div className={`font-semibold font-mono mt-0.5 ${isLight ? 'text-slate-800' : 'text-slate-200'}`}>
                  {selectedEvent.confidence || '91%'}
                </div>
              </div>
              <div>
                <span className={`text-[10px] uppercase font-mono tracking-wider ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                  EFI Max
                </span>
                <div className={`font-semibold font-mono mt-0.5 ${isLight ? 'text-sky-700' : 'text-cyan-300'}`}>
                  {selectedEvent.efi || '+2.31'}
                </div>
              </div>
              <div>
                <span className={`text-[10px] uppercase font-mono tracking-wider ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                  Peak Intensity
                </span>
                <div className={`font-semibold font-mono mt-0.5 ${isLight ? 'text-slate-800' : 'text-slate-200'}`}>
                  {selectedEvent.intensity || '222 mm/6h'}
                </div>
              </div>
              <div className="col-span-2">
                <span className={`text-[10px] uppercase font-mono tracking-wider ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                  Location
                </span>
                <div className={`font-semibold font-mono mt-0.5 ${isLight ? 'text-slate-800' : 'text-slate-200'}`}>
                  {selectedEvent.lat.toFixed(2)}° N, {selectedEvent.lon.toFixed(2)}° E
                </div>
              </div>
              <div className="col-span-2">
                <span className={`text-[10px] uppercase font-mono tracking-wider ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                  Valid Time
                </span>
                <div className={`font-semibold font-mono mt-0.5 ${isLight ? 'text-slate-800' : 'text-slate-200'}`}>
                  {formatUtc(currentValidTime)} ({formatIst(currentValidTime)})
                </div>
              </div>
            </div>

            <div className="pt-3 flex items-center justify-between gap-2">
              <Link
                to={`/events/${selectedEvent.id}`}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-bold font-mono transition"
              >
                <span>VIEW EVENT</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </Link>
              <button
                onClick={() => centerOnEvent(selectedEvent.lat, selectedEvent.lon)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-mono transition ${
                  isLight
                    ? 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                    : 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                }`}
              >
                Center View
              </button>
            </div>
          </div>
        )}
      </div>

      {/* BOTTOM: Integrated Forecast Time Controller */}
      <div
        className={`w-full border-t px-4 py-3 flex flex-col md:flex-row items-center justify-between gap-3 z-10 transition-colors ${
          isLight
            ? 'bg-white border-slate-200 text-slate-800 shadow-sm'
            : 'bg-slate-950 border-slate-800/80 text-slate-200'
        }`}
      >
        {/* Playback Step Controls */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => {
              pauseTimeline();
              stepTimeline(-1);
            }}
            disabled={timelineIndex <= 0}
            className={`p-1.5 rounded-lg border disabled:opacity-40 transition ${
              isLight
                ? 'bg-slate-100 border-slate-200 hover:bg-slate-200 text-slate-700'
                : 'bg-slate-900 border-slate-800 hover:bg-slate-800 text-slate-300'
            }`}
            title="Step Back One Lead Time"
            aria-label="Previous Lead Hour"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={toggleTimeline}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-mono text-xs font-bold transition shadow-sm"
            aria-label={timelinePlaying ? 'Pause forecast timeline' : 'Play forecast timeline'}
          >
            {timelinePlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{timelinePlaying ? 'PAUSE' : 'PLAY'}</span>
          </button>
          <button
            onClick={() => {
              pauseTimeline();
              stepTimeline(1);
            }}
            disabled={timelineIndex >= timelineLeads.length - 1}
            className={`p-1.5 rounded-lg border disabled:opacity-40 transition ${
              isLight
                ? 'bg-slate-100 border-slate-200 hover:bg-slate-200 text-slate-700'
                : 'bg-slate-900 border-slate-800 hover:bg-slate-800 text-slate-300'
            }`}
            title="Step Forward One Lead Time"
            aria-label="Next Lead Hour"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* Time Slider */}
        <div className="flex-1 w-full max-w-xl mx-2 flex flex-col gap-1">
          <div
            className={`flex justify-between items-center text-[10px] font-mono ${
              isLight ? 'text-slate-500' : 'text-slate-400'
            }`}
          >
            <span>T+00h</span>
            <span className={isLight ? 'text-cyan-700 font-bold' : 'text-cyan-400 font-bold'}>
              FORECAST TIMELINE: {curLead !== undefined ? leadLabel(curLead) : '+00h'}
            </span>
            <span>T+{timelineLeads[timelineLeads.length - 1] ?? 120}h</span>
          </div>
          <input
            id="globe-timeline-slider"
            type="range"
            min={0}
            max={Math.max(0, timelineLeads.length - 1)}
            value={timelineIndex}
            onChange={(e) => {
              pauseTimeline();
              const l = timelineLeads[Number(e.target.value)];
              if (l !== undefined) setLead(l);
            }}
            className={`w-full accent-cyan-600 cursor-pointer h-1.5 rounded-lg ${
              isLight ? 'bg-slate-200' : 'bg-slate-800'
            }`}
            aria-label="Forecast Lead Slider"
          />
        </div>

        {/* Valid Time Display */}
        <div
          className={`flex items-center gap-3 font-mono text-xs px-3 py-1.5 rounded-lg border shrink-0 ${
            isLight
              ? 'bg-slate-50 border-slate-200 text-slate-800'
              : 'bg-slate-900 border-slate-800 text-slate-200'
          }`}
        >
          <div className={`text-[10px] uppercase tracking-wider ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
            VALID TIME
          </div>
          <div className={isLight ? 'text-cyan-700 font-bold' : 'text-cyan-300 font-bold'}>
            {formatUtc(currentValidTime)}
          </div>
        </div>
      </div>
    </div>
  );
};
