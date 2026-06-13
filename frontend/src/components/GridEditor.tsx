'use client';

import { useState, useCallback, useRef } from 'react';
import { CellConfig, MapConfig } from '@/types';

type CellType = 'empty' | 'obstacle' | 'resource' | 'spawn' | 'target';

const CELL_COLORS: Record<CellType, string> = {
  empty: '#e5e7eb',
  obstacle: '#374151',
  resource: '#10b981',
  spawn: '#3b82f6',
  target: '#f59e0b',
};

const CELL_LABELS: Record<CellType, string> = {
  empty: '空地',
  obstacle: '障碍物',
  resource: '资源点',
  spawn: '出生点',
  target: '目标点',
};

interface GridEditorProps {
  mapConfig: MapConfig;
  onChange: (config: MapConfig) => void;
  readOnly?: boolean;
  agentPositions?: { id: number; x: number; y: number }[];
  highlightCells?: { x: number; y: number; color: string }[];
}

export default function GridEditor({ mapConfig, onChange, readOnly = false, agentPositions, highlightCells }: GridEditorProps) {
  const [selectedTool, setSelectedTool] = useState<CellType>('obstacle');
  const [spawnTeam, setSpawnTeam] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const getCellAt = useCallback((x: number, y: number): CellConfig | undefined => {
    return mapConfig.cells.find((c) => c.x === x && c.y === y);
  }, [mapConfig.cells]);

  const getCellType = useCallback((x: number, y: number): CellType => {
    const cell = getCellAt(x, y);
    return cell?.type || 'empty';
  }, [getCellAt]);

  const paintCell = useCallback((x: number, y: number) => {
    if (readOnly) return;
    if (x < 0 || x >= mapConfig.width || y < 0 || y >= mapConfig.height) return;

    const newCells = mapConfig.cells.filter((c) => !(c.x === x && c.y === y));

    if (selectedTool !== 'empty') {
      const newCell: CellConfig = { x, y, type: selectedTool };
      if (selectedTool === 'spawn') {
        newCell.team = spawnTeam;
      }
      newCells.push(newCell);
    }

    onChange({ ...mapConfig, cells: newCells });
  }, [mapConfig, selectedTool, spawnTeam, onChange, readOnly]);

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const cellSize = Math.min(
      (canvas.width - 40) / mapConfig.width,
      (canvas.height - 40) / mapConfig.height,
      40
    );
    const offsetX = (canvas.width - cellSize * mapConfig.width) / 2;
    const offsetY = (canvas.height - cellSize * mapConfig.height) / 2;

    const x = Math.floor((e.clientX - rect.left - offsetX) / cellSize);
    const y = Math.floor((e.clientY - rect.top - offsetY) / cellSize);
    paintCell(x, y);
  }, [mapConfig, paintCell]);

  const draw = useCallback((ctx: CanvasRenderingContext2D) => {
    const cellSize = Math.min(
      (ctx.canvas.width - 40) / mapConfig.width,
      (ctx.canvas.height - 40) / mapConfig.height,
      40
    );
    const offsetX = (ctx.canvas.width - cellSize * mapConfig.width) / 2;
    const offsetY = (ctx.canvas.height - cellSize * mapConfig.height) / 2;

    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);

    for (let y = 0; y < mapConfig.height; y++) {
      for (let x = 0; x < mapConfig.width; x++) {
        const px = offsetX + x * cellSize;
        const py = offsetY + y * cellSize;
        const cellType = getCellType(x, y);

        ctx.fillStyle = CELL_COLORS[cellType];
        ctx.fillRect(px, py, cellSize - 1, cellSize - 1);

        if (cellType === 'spawn') {
          const cell = getCellAt(x, y);
          ctx.fillStyle = '#fff';
          ctx.font = `${Math.max(cellSize * 0.4, 8)}px monospace`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(`S${cell?.team ?? 0}`, px + cellSize / 2, py + cellSize / 2);
        }
        if (cellType === 'target') {
          ctx.fillStyle = '#fff';
          ctx.font = `${Math.max(cellSize * 0.4, 8)}px monospace`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText('T', px + cellSize / 2, py + cellSize / 2);
        }
        if (cellType === 'resource') {
          ctx.fillStyle = '#fff';
          ctx.font = `${Math.max(cellSize * 0.4, 8)}px monospace`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText('R', px + cellSize / 2, py + cellSize / 2);
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
        ctx.font = `bold ${Math.max(cellSize * 0.3, 7)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${i}`, px + cellSize / 2, py + cellSize / 2);
      });
    }

    if (highlightCells) {
      highlightCells.forEach((hc) => {
        const px = offsetX + hc.x * cellSize;
        const py = offsetY + hc.y * cellSize;
        ctx.fillStyle = hc.color + '88';
        ctx.fillRect(px, py, cellSize - 1, cellSize - 1);
      });
    }
  }, [mapConfig, getCellType, getCellAt, agentPositions, highlightCells]);

  return (
    <div className="flex flex-col gap-3">
      {!readOnly && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-slate-400">画笔工具:</span>
          {(Object.keys(CELL_COLORS) as CellType[]).map((type) => (
            <button
              key={type}
              onClick={() => setSelectedTool(type)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                selectedTool === type
                  ? 'ring-2 ring-blue-400 bg-slate-700'
                  : 'bg-slate-800 hover:bg-slate-700'
              }`}
            >
              <span
                className="w-4 h-4 rounded"
                style={{ backgroundColor: CELL_COLORS[type] }}
              />
              {CELL_LABELS[type]}
            </button>
          ))}
          {selectedTool === 'spawn' && (
            <div className="flex items-center gap-2 ml-2">
              <span className="text-sm text-slate-400">阵营:</span>
              <input
                type="number"
                min={0}
                max={7}
                value={spawnTeam}
                onChange={(e) => setSpawnTeam(parseInt(e.target.value) || 0)}
                className="input-field w-16 text-sm"
              />
            </div>
          )}
        </div>
      )}

      <canvas
        ref={canvasRef}
        width={800}
        height={600}
        onClick={handleCanvasClick}
        onMouseDown={() => setIsDragging(true)}
        onMouseUp={() => setIsDragging(false)}
        onMouseLeave={() => setIsDragging(false)}
        className="rounded-lg border border-slate-600 cursor-crosshair"
      />

      <div className="flex items-center gap-4 text-xs text-slate-400">
        <span>地图: {mapConfig.width} × {mapConfig.height}</span>
        <span>障碍: {mapConfig.cells.filter((c) => c.type === 'obstacle').length}</span>
        <span>资源: {mapConfig.cells.filter((c) => c.type === 'resource').length}</span>
        <span>出生点: {mapConfig.cells.filter((c) => c.type === 'spawn').length}</span>
        <span>目标点: {mapConfig.cells.filter((c) => c.type === 'target').length}</span>
      </div>
    </div>
  );
}
