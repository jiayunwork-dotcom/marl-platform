import { create } from 'zustand';
import { Environment, Experiment, AlgorithmInfo } from '@/types';

interface AppState {
  environments: Environment[];
  experiments: Experiment[];
  algorithms: AlgorithmInfo[];
  selectedEnvId: number | null;
  selectedExpId: number | null;
  setEnvironments: (envs: Environment[]) => void;
  setExperiments: (exps: Experiment[]) => void;
  setAlgorithms: (algos: AlgorithmInfo[]) => void;
  setSelectedEnvId: (id: number | null) => void;
  setSelectedExpId: (id: number | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  environments: [],
  experiments: [],
  algorithms: [],
  selectedEnvId: null,
  selectedExpId: null,
  setEnvironments: (environments) => set({ environments }),
  setExperiments: (experiments) => set({ experiments }),
  setAlgorithms: (algorithms) => set({ algorithms }),
  setSelectedEnvId: (selectedEnvId) => set({ selectedEnvId }),
  setSelectedExpId: (selectedExpId) => set({ selectedExpId }),
}));
