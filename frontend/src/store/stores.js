// frontend/src/store/stores.js
import { create } from "zustand";

export { useAuthStore } from "./authStore";
export { useResourceStore } from "./resourceStore";
export { useTransactionStore } from "./transactionStore";
export { useConflictStore } from "./conflictStore";

export const useBedStore = create((set) => ({
  bedGrid     : [],            // floor-wise grouped beds
  selectedBed : null,          // bed selected for allocation

  setBedGrid      : (gridOrUpdater) =>
    set((state) => ({
      bedGrid:
        typeof gridOrUpdater === "function"
          ? gridOrUpdater(state.bedGrid)
          : gridOrUpdater || [],
    })),
  setSelectedBed  : (bed)  => set({ selectedBed: bed }),
  clearSelectedBed: ()     => set({ selectedBed: null }),

  // Live update: single bed status change from WebSocket
  updateBedStatus: (bedId, newStatus, extras = {}) =>
    set((state) => ({
      bedGrid: (state.bedGrid || []).map((floor) => ({
        ...floor,
        beds: (floor.beds || []).map((bed) =>
          bed.id === bedId ? { ...bed, status: newStatus, ...extras } : bed
        ),
      })),
    })),
}));
