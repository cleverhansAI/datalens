"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { ViewResult } from "@/lib/api";

export function StatsPanels({
  view,
  selectedClasses,
  onClassToggle,
  onClearClassSelection,
  embedded = false,
  showImageMetrics = true
}: {
  view: ViewResult | null;
  selectedClasses: string[];
  onClassToggle: (className: string) => void;
  onClearClassSelection: () => void;
  embedded?: boolean;
  showImageMetrics?: boolean;
}) {
  const classEntries = Object.entries(view?.class_distribution ?? {});
  const hasClassSelection = selectedClasses.length > 0;
  const selectedClassSet = new Set(selectedClasses);
  const imageMetrics = useMemo(() => {
    if (!view || view.images.length === 0) {
      return {
        imageCount: view?.total ?? 0,
        avgWidth: 0,
        avgHeight: 0,
        avgAspectRatio: 0
      };
    }

    const totals = view.images.reduce(
      (accumulator, image) => ({
        width: accumulator.width + image.width,
        height: accumulator.height + image.height,
        aspectRatio: accumulator.aspectRatio + image.aspect_ratio
      }),
      { width: 0, height: 0, aspectRatio: 0 }
    );
    const imageCount = view.images.length;

    return {
      imageCount: view.total,
      avgWidth: totals.width / imageCount,
      avgHeight: totals.height / imageCount,
      avgAspectRatio: totals.aspectRatio / imageCount
    };
  }, [view]);
  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(2, 6, 23, 0.94)",
      borderColor: "rgba(56, 189, 248, 0.25)",
      textStyle: { color: "#e2e8f0" }
    },
    grid: { left: 56, right: 20, top: 30, bottom: 48, containLabel: true },
    xAxis: {
      type: "category",
      data: classEntries.map(([k]) => k),
      axisLabel: { color: "#94a3b8", rotate: 20 },
      axisLine: { lineStyle: { color: "#334155" } }
    },
    yAxis: {
      type: "value",
      name: "Instances",
      nameLocation: "middle",
      nameGap: 42,
      nameTextStyle: { color: "#cbd5e1", fontSize: 12, fontWeight: 600 },
      minInterval: 1,
      axisLabel: {
        color: "#cbd5e1",
        fontSize: 12,
        formatter: (value: number) => `${Math.round(value)}`
      },
      axisLine: { show: true, lineStyle: { color: "#475569" } },
      splitLine: { lineStyle: { color: "rgba(51, 65, 85, 0.45)" } }
    },
    series: [
      {
        type: "bar",
        data: classEntries.map(([className, value]) => ({
          value,
          itemStyle: {
            color: hasClassSelection
              ? selectedClassSet.has(className)
                ? "#38bdf8"
                : "rgba(100, 116, 139, 0.5)"
              : "#22c55e",
            borderRadius: [8, 8, 0, 0],
            shadowBlur: selectedClassSet.has(className) ? 16 : 12,
            shadowColor: selectedClassSet.has(className) ? "rgba(56, 189, 248, 0.28)" : "rgba(34, 197, 94, 0.22)"
          }
        })),
        itemStyle: {
          borderRadius: [8, 8, 0, 0],
          shadowBlur: 12,
          shadowColor: "rgba(34, 197, 94, 0.22)"
        },
        emphasis: {
          itemStyle: {
            color: "#38bdf8"
          }
        }
      }
    ]
  };
  const panelClassName = embedded ? "rounded-lg border border-slate-800 bg-slate-900/60 p-2.5" : "card p-4";

  return (
    <div className={`grid grid-cols-1 gap-2 ${showImageMetrics ? "xl:grid-cols-[minmax(0,300px)_minmax(0,1fr)]" : ""}`}>
      {showImageMetrics ? (
        <div className={panelClassName}>
          <h3 className="panel-title text-sm font-semibold">Image Metrics</h3>
          <div className="mt-2 grid grid-cols-2 gap-1.5 text-sm">
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2">
              <div className="subtle-label mb-0.5 text-[10px] uppercase tracking-[0.22em]">Count</div>
              <div className="text-base font-semibold text-slate-100">{imageMetrics.imageCount}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2">
              <div className="subtle-label mb-0.5 text-[10px] uppercase tracking-[0.22em]">Avg Width</div>
              <div className="text-base font-semibold text-cyan-200">{imageMetrics.avgWidth.toFixed(0)}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2">
              <div className="subtle-label mb-0.5 text-[10px] uppercase tracking-[0.22em]">Avg Height</div>
              <div className="text-base font-semibold text-cyan-200">{imageMetrics.avgHeight.toFixed(0)}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2">
              <div className="subtle-label mb-0.5 text-[10px] uppercase tracking-[0.22em]">Aspect Ratio</div>
              <div className="text-base font-semibold text-emerald-200">{imageMetrics.avgAspectRatio.toFixed(2)}</div>
            </div>
          </div>
        </div>
      ) : null}
      <div className={panelClassName}>
        <div className="mb-1.5 flex items-center justify-between gap-3">
          <h3 className="panel-title text-sm font-semibold">Class Distribution</h3>
          <button
            type="button"
            className="rounded-full border border-slate-700 bg-slate-950/80 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400"
            onClick={onClearClassSelection}
          >
            {hasClassSelection ? `${selectedClasses.length} classes selected` : "All classes"}
          </button>
        </div>
        <ReactECharts
          option={option}
          style={{ height: embedded ? (showImageMetrics ? 190 : 240) : 250 }}
          onEvents={{
            click: (params: { name?: string }) => {
              if (params.name) {
                onClassToggle(params.name);
              }
            }
          }}
        />
      </div>
    </div>
  );
}
