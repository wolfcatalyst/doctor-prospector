import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface ExportQueueItem {
  hospitalName: string;
  hospitalId: string;
  physicianNpis: string[];
  addedAt: string;
}

interface ExportQueueState {
  items: ExportQueueItem[];
  addItem: (item: ExportQueueItem) => void;
  removeItem: (hospitalId: string) => void;
  clearAll: () => void;
  count: () => number;
}

export const useExportQueueStore = create<ExportQueueState>()(
  persist(
    (set, get) => ({
      items: [],

      addItem: (item) =>
        set((state) => ({
          items: [
            ...state.items.filter((i) => i.hospitalId !== item.hospitalId),
            item,
          ],
        })),

      removeItem: (hospitalId) =>
        set((state) => ({
          items: state.items.filter((i) => i.hospitalId !== hospitalId),
        })),

      clearAll: () => set({ items: [] }),

      count: () => get().items.length,
    }),
    {
      name: "doctor-prospector-export-queue",
    }
  )
);
