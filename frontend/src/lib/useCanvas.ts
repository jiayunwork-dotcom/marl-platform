'use client';

import { useEffect, useRef } from 'react';
import { MapConfig } from '@/types';

type CellType = 'empty' | 'obstacle' | 'resource' | 'spawn' | 'target';

const CELL_COLORS: Record<CellType, string> = {
  empty: '#e5e7eb',
  obstacle: '#374151',
  resource: '#10b981',
  spawn: '#3b82f6',
  target: '#f59e0b',
};

interface UseCanvasRenderProps {
  mapConfig: MapConfig;
  agentPositions?: { id: number; x: number; y: number }[];
  heatmap?: number[][];
  qMap?: number[][];
}

export function useCanvasRender({ mapConfig, agentPositions, heatmap, qMap }: UseCanvasRenderProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const cellSize = Math.min(
      (canvas.width - 40) / mapConfig.width,
      (canvas.height - 40) / mapConfig.height,
      40
    );
    const offsetX = (canvas.width - cellSize * mapConfig.width) / 2;
    const offsetY = (canvas.height - cellSize * mapConfig.height) / 2;

    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (let y = 0; y < mapConfig.height; y++) {
      for (let x = 0; x < mapConfig.width; x++) {
        const px = offsetX + x * cellSize;
        const py = offsetY + y * cellSize;
        const cell = mapConfig.cells.find((c) => c.x === x && c.y === y);
        const cellType = cell?.type || 'empty';

        if (heatmap && heatmap[y]?.[x] !== undefined) {
          const intensity = Math.min(1, heatmap[y][x]);
          ctx.fillStyle = `rgba(239, 68, 68, ${intensity})`;
          ctx.fillRect(px, py, cellSize - 1, cellSize - 1);
        } else if (qMap && qMap[y]?.[x] !== undefined) {
          const val = Math.min(1, Math.max(0, qMap[y][x]));
          const r = Math.floor(val * 255);
          const b = Math.floor((1 - val) * 255);
          ctx.fillStyle = `rgb(${r}, 50, ${b})`;
          ctx.fillRect(px, py, cellSize - 1, cellSize - 1);
        } else {
          ctx.fillStyle = CELL_COLORS[cellType];
          ctx.fillRect(px, py, cellSize - 1, cellSize - 1);
        }

        if (cellType === 'spawn' || cellType === 'target' || cellType === 'resource') {
          ctx.fillStyle = '#fff';
          ctx.font = `${Math.max(cellSize * 0.35, 8)}px monospace`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          const label = cellType === 'spawn' ? 'S' : cellType === 'target' ? 'T' : 'R';
          ctx.fillText(label, px + cellSize / 2, py + cellSize / 2);
        }
      }
    }

    if (agentPositions) {
      const agentColors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];
      agentPositions.forEach((agent, i) => {
        const px = offsetX + agent.x * cellSize;
        const py = offsetY + agent.y * cellSize;
        ctx.fillStyle = agentColors[i % agentColors.length];
        ctx.beginPath();
        ctx.arc(px + cellSize / 2, py + cellSize / 2, cellSize * 0.35, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#fff';
        ctx.font = `bold ${Math.max(cellSize * 0.25, 7)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${i}`, px + cellSize / 2, py + cellSize / 2);
      });
    }
  }, [mapConfig, agentPositions, heatmap, qMap]);

  return canvasRef;
}
