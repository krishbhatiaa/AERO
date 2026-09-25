import React from 'react';
import { Globe3D } from '../features/Globe3D';
import { Globe as GlobeIcon, ShieldAlert, Cpu, Sparkles } from 'lucide-react';

export const GlobePage: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/60 p-6 rounded-xl border border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-3">
            <GlobeIcon className="w-7 h-7 text-cyan-400" />
            3D Global Anomaly Globe
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Spatio-temporal extreme weather anomaly visualization projected on a 3D spherical Earth mesh.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-300 font-mono bg-slate-950 px-4 py-2 rounded-lg border border-slate-700">
          <Cpu className="w-4 h-4 text-cyan-400" />
          <span>Spherical Grid Resolution: 0.25° (~28 km)</span>
        </div>
      </div>

      {/* 3D Globe Component */}
      <Globe3D />

      {/* Analytics Summary Cards below 3D globe */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900/40 p-4 rounded-xl border border-slate-800 flex items-start gap-3">
          <ShieldAlert className="w-6 h-6 text-red-400 shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-semibold text-slate-200">Tracked Cyclonic Trajectories</h4>
            <p className="text-xs text-slate-400 mt-1">
              Active Kalman-filtered tracks projected over spherical coordinates with constant-velocity extrapolation.
            </p>
          </div>
        </div>

        <div className="bg-slate-900/40 p-4 rounded-xl border border-slate-800 flex items-start gap-3">
          <Sparkles className="w-6 h-6 text-cyan-400 shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-semibold text-slate-200">Diffusive Downscaling Projection</h4>
            <p className="text-xs text-slate-400 mt-1">
              Probabilistic EDM diffusion downscaler samples fine precipitation fields (12 km to 5 km).
            </p>
          </div>
        </div>

        <div className="bg-slate-900/40 p-4 rounded-xl border border-slate-800 flex items-start gap-3">
          <GlobeIcon className="w-6 h-6 text-emerald-400 shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-semibold text-slate-200">Spherical Area Conservation</h4>
            <p className="text-xs text-slate-400 mt-1">
              Spherical cell area cos(latitude) scaling ensures zero distortion towards polar regions.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
