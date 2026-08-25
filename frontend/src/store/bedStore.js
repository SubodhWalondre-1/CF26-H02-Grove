import { create } from "zustand";

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
