"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { Board, type GalleryDensity } from "@/features/gallery/Board";
import { StatsPanels } from "@/features/dashboards/StatsPanels";
import { EmbeddingMap } from "@/features/embeddings/EmbeddingMap";
import {
  api,
  type Dataset,
  type EmbeddingPoint,
  type ImageStats,
  type ObjectStats,
  type SavedView,
  type TaskStatus as ApiTaskStatus,
  type ViewFilter,
  type ViewQueryRequest,
  type ViewSpec,
  type ViewResult
} from "@/lib/api";

type RangeFilterState = {
  min: number;
  max: number;
};

const FALLBACK_BBOX_LIMIT = 1024;
const FULL_VIEW_PAGE_SIZE = 100000;
const GALLERY_PAGE_SIZE = 120;
const DEFAULT_GROUP_BY = "directory";
type GroupByValue = "directory" | "class" | "image_size_bucket";

export default function HomePage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [view, setView] = useState<ViewResult | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const galleryPageRef = useRef(1);
  const viewRef = useRef<ViewResult | null>(null);
  const [imageStats, setImageStats] = useState<ImageStats | null>(null);
  const [objectStats, setObjectStats] = useState<ObjectStats | null>(null);
  const [projection, setProjection] = useState<EmbeddingPoint[]>([]);
  const [embeddingSelection, setEmbeddingSelection] = useState<number[]>([]);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [savedViewsLoading, setSavedViewsLoading] = useState<boolean>(false);
  const [selectedSavedViewId, setSelectedSavedViewId] = useState<string>("");
  const [groupBy, setGroupBy] = useState<GroupByValue>(DEFAULT_GROUP_BY);
  const [directoryFilter, setDirectoryFilter] = useState<string[]>([]);
  const [classFilter, setClassFilter] = useState<string[]>([]);
  const [density, setDensity] = useState<GalleryDensity>("comfortable");
  const [bboxWidthRange, setBboxWidthRange] = useState<RangeFilterState>({ min: 0, max: FALLBACK_BBOX_LIMIT });
  const [bboxHeightRange, setBboxHeightRange] = useState<RangeFilterState>({ min: 0, max: FALLBACK_BBOX_LIMIT });
  const [sessionSummaryCollapsed, setSessionSummaryCollapsed] = useState<boolean>(true);
  const [currentViewCollapsed, setCurrentViewCollapsed] = useState<boolean>(true);
  const [missionControlsCollapsed, setMissionControlsCollapsed] = useState<boolean>(true);
  const [filtersCollapsed, setFiltersCollapsed] = useState<boolean>(true);
  const [actionsCollapsed, setActionsCollapsed] = useState<boolean>(true);
  const [directoryFilterCollapsed, setDirectoryFilterCollapsed] = useState<boolean>(true);
  const [classFilterCollapsed, setClassFilterCollapsed] = useState<boolean>(true);
  const [bboxFiltersCollapsed, setBboxFiltersCollapsed] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [datasetsLoading, setDatasetsLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<string>("");
  const [embeddingTaskId, setEmbeddingTaskId] = useState<string | null>(null);
  const [embeddingTaskStatus, setEmbeddingTaskStatus] = useState<ApiTaskStatus | null>(null);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const pendingDatasetIdRef = useRef("");
  const pendingViewRef = useRef<{ datasetId: string; spec: ViewSpec } | null>(null);

  const refreshDatasets = useCallback(async () => {
    setDatasetsLoading(true);
    try {
      const nextDatasets = await api.listDatasets();
      setDatasets(nextDatasets);
    } catch (e) {
      setMessage(String(e));
    } finally {
      setDatasetsLoading(false);
    }
  }, []);

  const refreshSavedViews = useCallback(async (activeDatasetId: string) => {
    if (!activeDatasetId) {
      setSavedViews([]);
      return;
    }
    setSavedViewsLoading(true);
    try {
      setSavedViews(await api.listSavedViews(activeDatasetId));
    } catch (e) {
      setMessage(String(e));
    } finally {
      setSavedViewsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshDatasets();
    const timer = window.setInterval(() => {
      void refreshDatasets();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refreshDatasets]);

  useEffect(() => {
    let cancelled = false;
    void api
      .getSession()
      .then((session) => {
        if (cancelled) {
          return;
        }
        if (session.dataset_id) {
          pendingDatasetIdRef.current = session.dataset_id;
        }
        if (session.dataset_id && session.view) {
          pendingViewRef.current = { datasetId: session.dataset_id, spec: session.view };
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) {
          setSessionLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!sessionLoaded || datasetId || datasets.length === 0) {
      return;
    }
    const preferred = pendingDatasetIdRef.current;
    const match = datasets.some((dataset) => dataset.id === preferred);
    setDatasetId(match ? preferred : datasets[0].id);
  }, [datasetId, datasets, sessionLoaded]);

  useEffect(() => {
    setDirectoryFilter([]);
    setClassFilter([]);
    setBboxWidthRange({ min: 0, max: FALLBACK_BBOX_LIMIT });
    setBboxHeightRange({ min: 0, max: FALLBACK_BBOX_LIMIT });
    setView(null);
    setImageStats(null);
    setObjectStats(null);
    setSavedViews([]);
    setSelectedSavedViewId("");
    setProjection([]);
    setEmbeddingSelection([]);
    setEmbeddingTaskId(null);
    setEmbeddingTaskStatus(null);
    setMessage("");
  }, [datasetId]);

  const activeDataset = useMemo(() => datasets.find((d) => d.id === datasetId), [datasets, datasetId]);
  const activeSavedView = useMemo(
    () => savedViews.find((savedView) => savedView.id === selectedSavedViewId) ?? null,
    [savedViews, selectedSavedViewId]
  );
  const bboxWidthLimit = useMemo(
    () => Math.max(1, Math.ceil(objectStats?.bbox_width_max ?? 0) || FALLBACK_BBOX_LIMIT),
    [objectStats]
  );
  const bboxHeightLimit = useMemo(
    () => Math.max(1, Math.ceil(objectStats?.bbox_height_max ?? 0) || FALLBACK_BBOX_LIMIT),
    [objectStats]
  );
  const directoryOptions = useMemo(
    () => Object.entries(imageStats?.directory_distribution ?? {}).sort(([left], [right]) => left.localeCompare(right)),
    [imageStats]
  );
  const directoryFilterSummary = useMemo(() => formatDirectoryFilterSummary(directoryFilter), [directoryFilter]);
  const classOptions = useMemo(
    () =>
      Object.entries(objectStats?.class_distribution ?? {}).sort(
        ([leftClass, leftCount], [rightClass, rightCount]) => rightCount - leftCount || leftClass.localeCompare(rightClass)
      ),
    [objectStats]
  );
  const classFilterSummary = useMemo(() => formatClassFilterSummary(classFilter), [classFilter]);
  const bboxFilterSummary = useMemo(
    () => formatBboxFilterSummary(bboxWidthRange, bboxWidthLimit, bboxHeightRange, bboxHeightLimit),
    [bboxHeightLimit, bboxHeightRange, bboxWidthLimit, bboxWidthRange]
  );
  const currentViewSpec = useMemo<ViewSpec>(
    () => ({
      filters: buildCurrentFilters(directoryFilter, classFilter, bboxWidthRange, bboxWidthLimit, bboxHeightRange, bboxHeightLimit),
      group_by: groupBy,
      sort_by: null,
      sort_desc: false,
      page: 1,
      page_size: FULL_VIEW_PAGE_SIZE
    }),
    [bboxHeightLimit, bboxHeightRange, bboxWidthLimit, bboxWidthRange, classFilter, directoryFilter, groupBy]
  );
  const isViewUpdating = loading;
  const hasActiveViewFilters =
    currentViewSpec.filters.length > 0 || currentViewSpec.group_by !== DEFAULT_GROUP_BY;
  const currentViewTitle = activeSavedView?.name ?? (hasActiveViewFilters ? "Filtered Dataset View" : "Full Dataset View");
  const currentViewSummary = useMemo(() => {
    const parts: string[] = [];
    if (activeSavedView) {
      parts.push(`Saved view: ${activeSavedView.name}`);
    }
    if (directoryFilter.length > 0) {
      parts.push(`Directories: ${directoryFilterSummary}`);
    }
    if (classFilter.length > 0) {
      parts.push(`Classes: ${classFilterSummary}`);
    }
    if (!isFullRange(bboxWidthRange, bboxWidthLimit) || !isFullRange(bboxHeightRange, bboxHeightLimit)) {
      parts.push(`Boxes: ${bboxFilterSummary}`);
    }
    if (groupBy !== DEFAULT_GROUP_BY) {
      parts.push(`Group by: ${groupBy}`);
    }
    return parts;
  }, [
    activeSavedView,
    bboxFilterSummary,
    bboxHeightLimit,
    bboxHeightRange,
    bboxWidthLimit,
    bboxWidthRange,
    classFilter.length,
    classFilterSummary,
    directoryFilter.length,
    directoryFilterSummary,
    groupBy
  ]);
  const boardView = useMemo(
    () =>
      embeddingSelection.length > 0
        ? filterViewToImageIds(view, new Set<number>(embeddingSelection))
        : view,
    [embeddingSelection, view]
  );
  const isEmbeddingsRunning =
    embeddingTaskStatus?.state === "queued" || embeddingTaskStatus?.state === "running";
  const currentViewStatusLabel = isEmbeddingsRunning
    ? "Embedding job running"
    : isViewUpdating
      ? "Loading view"
      : activeDataset
        ? "Ready"
        : "Idle";
  const currentViewMetrics = useMemo(() => {
    if (!view) {
      return { avgWidth: 0, avgHeight: 0, avgAspectRatio: 0 };
    }
    if (view.avg_width !== undefined || view.avg_height !== undefined || view.avg_aspect_ratio !== undefined) {
      return {
        avgWidth: view.avg_width ?? 0,
        avgHeight: view.avg_height ?? 0,
        avgAspectRatio: view.avg_aspect_ratio ?? 0
      };
    }
    if (view.images.length === 0) {
      return { avgWidth: 0, avgHeight: 0, avgAspectRatio: 0 };
    }
    const totals = view.images.reduce(
      (accumulator, image) => ({
        width: accumulator.width + image.width,
        height: accumulator.height + image.height,
        aspectRatio: accumulator.aspectRatio + image.aspect_ratio
      }),
      { width: 0, height: 0, aspectRatio: 0 }
    );
    return {
      avgWidth: totals.width / view.images.length,
      avgHeight: totals.height / view.images.length,
      avgAspectRatio: totals.aspectRatio / view.images.length
    };
  }, [view]);

  useEffect(() => {
    setBboxWidthRange((prev) => clampRange(prev, bboxWidthLimit));
  }, [bboxWidthLimit]);

  useEffect(() => {
    setBboxHeightRange((prev) => clampRange(prev, bboxHeightLimit));
  }, [bboxHeightLimit]);

  const toggleClassFilter = useCallback((className: string) => {
    setClassFilter((current) =>
      current.includes(className) ? current.filter((value) => value !== className) : [...current, className]
    );
  }, []);

  const applyViewSpec = useCallback(
    (spec: ViewSpec) => {
      setGroupBy(isGroupByValue(spec.group_by) ? spec.group_by : DEFAULT_GROUP_BY);
      setDirectoryFilter(extractDirectoryFilter(spec.filters));
      setClassFilter(extractClassFilter(spec.filters));
      setBboxWidthRange(extractRangeFromFilters(spec.filters, "bbox_width", bboxWidthLimit));
      setBboxHeightRange(extractRangeFromFilters(spec.filters, "bbox_height", bboxHeightLimit));
      setProjection([]);
      setEmbeddingSelection([]);
    },
    [bboxHeightLimit, bboxWidthLimit]
  );

  useEffect(() => {
    if (!sessionLoaded || !datasetId) {
      return;
    }
    const pending = pendingViewRef.current;
    if (pending && pending.datasetId === datasetId) {
      pendingViewRef.current = null;
      applyViewSpec(pending.spec);
    }
    setSessionReady(true);
  }, [applyViewSpec, datasetId, sessionLoaded]);

  useEffect(() => {
    if (!sessionReady || !datasetId) {
      return;
    }
    const timer = window.setTimeout(() => {
      void api.saveSession({ dataset_id: datasetId, view: currentViewSpec }).catch(() => undefined);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [currentViewSpec, datasetId, sessionReady]);

  const buildViewRequest = useCallback(
    (spec: ViewSpec): ViewQueryRequest | ViewSpec => {
      if (activeSavedView && areViewSpecsEqual(activeSavedView.spec, spec)) {
        return {
          saved_view_id: activeSavedView.id,
          spec: {
            filters: [],
            group_by: null,
            sort_by: null,
            sort_desc: false,
            page: spec.page,
            page_size: spec.page_size
          }
        };
      }
      return spec;
    },
    [activeSavedView]
  );

  const loadView = useCallback(async () => {
    if (!datasetId) {
      return;
    }
    galleryPageRef.current = 1;
    setLoading(true);
    setMessage("Loading current view...");
    try {
      const result = await api.queryView(
        datasetId,
        buildViewRequest({ ...currentViewSpec, page: 1, page_size: GALLERY_PAGE_SIZE })
      );
      setView(result);
      setProjection([]);
      setEmbeddingSelection([]);
      setMessage(`Loaded ${result.total} images and ${result.total_annotations} annotations in the current view`);
    } catch (e) {
      setMessage(String(e));
    } finally {
      setLoading(false);
    }
  }, [buildViewRequest, currentViewSpec, datasetId]);

  const loadMoreImages = useCallback(async () => {
    if (!datasetId || !view || loadingMore || view.images.length >= view.total) {
      return;
    }
    const nextPage = galleryPageRef.current + 1;
    setLoadingMore(true);
    try {
      const result = await api.queryView(
        datasetId,
        buildViewRequest({ ...currentViewSpec, page: nextPage, page_size: GALLERY_PAGE_SIZE })
      );
      galleryPageRef.current = nextPage;
      setView((current) => (current ? appendGalleryPage(current, result) : result));
    } catch (e) {
      setMessage(String(e));
    } finally {
      setLoadingMore(false);
    }
  }, [buildViewRequest, currentViewSpec, datasetId, loadingMore, view]);

  useEffect(() => {
    if (datasetId) {
      let cancelled = false;
      setSavedViewsLoading(true);
      async function loadDatasetContext() {
        try {
          const [nextImageStats, nextObjectStats, nextSavedViews] = await Promise.all([
            api.imageStats(datasetId),
            api.objectStats(datasetId),
            api.listSavedViews(datasetId)
          ]);
          if (cancelled) {
            return;
          }
          setImageStats(nextImageStats);
          setObjectStats(nextObjectStats);
          setSavedViews(nextSavedViews);
        } catch (e) {
          if (!cancelled) {
            setMessage(String(e));
          }
        } finally {
          if (!cancelled) {
            setSavedViewsLoading(false);
          }
        }
      }
      void loadDatasetContext();
      return () => {
        cancelled = true;
      };
    }
  }, [datasetId]);

  useEffect(() => {
    if (!datasetId || !sessionReady) {
      return;
    }
    const timer = window.setTimeout(() => {
      void loadView();
    }, 150);
    return () => window.clearTimeout(timer);
  }, [datasetId, loadView, sessionReady]);

  useEffect(() => {
    if (!selectedSavedViewId) {
      return;
    }
    if (!activeSavedView) {
      setSelectedSavedViewId("");
      return;
    }
    if (!areViewSpecsEqual(activeSavedView.spec, currentViewSpec)) {
      setSelectedSavedViewId("");
    }
  }, [activeSavedView, currentViewSpec, selectedSavedViewId]);

  useEffect(() => {
    if (!embeddingTaskId || !isEmbeddingsRunning) {
      return;
    }

    const taskId = embeddingTaskId;
    let cancelled = false;

    async function pollTaskStatus() {
      try {
        const nextStatus = await api.taskStatus(taskId);
        if (cancelled) {
          return;
        }

        const runId = extractRunId(nextStatus.result);
        if (nextStatus.state === "done" && runId) {
          setMessage("Preparing embedding projection...");
          const projectionResult = await api.projection(runId);
          if (cancelled) {
            return;
          }
          setProjection(projectionResult.points);
          setEmbeddingSelection([]);
          setEmbeddingTaskStatus(nextStatus);
          const imageCount = extractImageCount(nextStatus.result);
          setMessage(`Embeddings ready${imageCount ? ` for ${imageCount} images` : ""} across ${Math.max(projectionResult.cluster_count, 1)} clusters`);
        } else if (nextStatus.state === "failed") {
          setEmbeddingTaskStatus(nextStatus);
          setMessage(nextStatus.message || "Embedding run failed");
        } else {
          setEmbeddingTaskStatus(nextStatus);
        }
      } catch (e) {
        if (!cancelled) {
          setMessage(String(e));
        }
      }
    }

    void pollTaskStatus();
    const interval = window.setInterval(() => {
      void pollTaskStatus();
    }, 400);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [embeddingTaskId, isEmbeddingsRunning]);

  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  useEffect(() => {
    if (!datasetId || embeddingSelection.length === 0) {
      return;
    }
    const loaded = new Set((viewRef.current?.images ?? []).map((image) => image.id));
    const missing = embeddingSelection.filter((id) => !loaded.has(id)).slice(0, 500);
    if (missing.length === 0) {
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const result = await api.queryView(datasetId, {
          filters: [{ field: "id", operator: "in", value: missing }],
          group_by: null,
          sort_by: null,
          sort_desc: false,
          page: 1,
          page_size: missing.length
        });
        if (!cancelled) {
          setView((current) => (current ? appendFocusedImages(current, result) : current));
        }
      } catch (e) {
        if (!cancelled) {
          setMessage(String(e));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [datasetId, embeddingSelection]);

  async function runEmbeddings() {
    if (!datasetId) {
      return;
    }
    setProjection([]);
    setEmbeddingSelection([]);
    setMessage("Starting embedding job...");
    try {
      const task = await api.runEmbeddingsAsync(buildEmbeddingRequest(datasetId, currentViewSpec, activeSavedView?.id ?? null));
      setEmbeddingTaskId(task.task_id);
      setEmbeddingTaskStatus(task);
      setMessage("Embedding job queued...");
    } catch (e) {
      setMessage(String(e));
    }
  }

  async function exportCurrentView() {
    if (!datasetId) {
      return;
    }
    try {
      const out = await api.exportCoco(datasetId, buildExportRequest(currentViewSpec, activeSavedView?.id ?? null));
      setMessage(`Exported to ${out.path}`);
    } catch (e) {
      setMessage(String(e));
    }
  }

  async function saveCurrentView() {
    if (!datasetId) {
      return;
    }
    const name = window.prompt("Saved view name", activeSavedView?.name ?? "");
    if (!name) {
      return;
    }
    const description = window.prompt("Saved view description (optional)", activeSavedView?.description ?? "") ?? "";
    try {
      const savedView = await api.createSavedView(datasetId, {
        name,
        description,
        spec: currentViewSpec
      });
      await refreshSavedViews(datasetId);
      setSelectedSavedViewId(savedView.id);
      setMessage(`Saved view "${savedView.name}" created`);
    } catch (e) {
      setMessage(String(e));
    }
  }

  async function updateCurrentSavedView() {
    if (!activeSavedView) {
      return;
    }
    try {
      const updatedView = await api.updateSavedView(activeSavedView.id, {
        name: activeSavedView.name,
        description: activeSavedView.description,
        spec: currentViewSpec
      });
      await refreshSavedViews(datasetId);
      setSelectedSavedViewId(updatedView.id);
      setMessage(`Updated saved view "${updatedView.name}"`);
    } catch (e) {
      setMessage(String(e));
    }
  }

  async function renameSavedView() {
    if (!activeSavedView) {
      return;
    }
    const name = window.prompt("Saved view name", activeSavedView.name);
    if (!name) {
      return;
    }
    const description = window.prompt("Saved view description (optional)", activeSavedView.description) ?? "";
    try {
      const updatedView = await api.updateSavedView(activeSavedView.id, { name, description });
      await refreshSavedViews(datasetId);
      setSelectedSavedViewId(updatedView.id);
      setMessage(`Renamed saved view to "${updatedView.name}"`);
    } catch (e) {
      setMessage(String(e));
    }
  }

  async function deleteActiveSavedView() {
    if (!activeSavedView) {
      return;
    }
    if (!window.confirm(`Delete saved view "${activeSavedView.name}"?`)) {
      return;
    }
    try {
      await api.deleteSavedView(activeSavedView.id);
      await refreshSavedViews(datasetId);
      setSelectedSavedViewId("");
      setMessage(`Deleted saved view "${activeSavedView.name}"`);
    } catch (e) {
      setMessage(String(e));
    }
  }

  const clearEmbeddingFocus = useCallback(() => {
    setEmbeddingSelection([]);
  }, []);

  const toggleDirectoryFilter = useCallback((directoryName: string) => {
    setDirectoryFilter((current) =>
      current.includes(directoryName)
        ? current.filter((value) => value !== directoryName)
        : [...current, directoryName]
    );
  }, []);

  const resetToFullDatasetView = useCallback(() => {
    setSelectedSavedViewId("");
    setDirectoryFilter([]);
    setClassFilter([]);
    setGroupBy(DEFAULT_GROUP_BY);
    setBboxWidthRange({ min: 0, max: bboxWidthLimit });
    setBboxHeightRange({ min: 0, max: bboxHeightLimit });
    setProjection([]);
    setEmbeddingSelection([]);
    setMessage("");
  }, [bboxHeightLimit, bboxWidthLimit]);

  const loadSavedView = useCallback(
    (savedViewId: string) => {
      setSelectedSavedViewId(savedViewId);
      const savedView = savedViews.find((candidate) => candidate.id === savedViewId);
      if (!savedView) {
        return;
      }
      applyViewSpec(savedView.spec);
      setMessage(`Loaded saved view "${savedView.name}"`);
    },
    [applyViewSpec, savedViews]
  );

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[1920px] flex-col px-4 py-6 sm:px-6 xl:px-8">
      <header className="mb-4 overflow-hidden rounded-[28px] border border-cyan-950/80 bg-slate-950/80 p-6 shadow-[0_24px_80px_rgba(2,6,23,0.45)] backdrop-blur-xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-4xl font-bold text-slate-50">DataLens</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              Inspect datasets, filter views, save views, and run embeddings.
            </p>
          </div>
          <div className="flex min-w-[220px] flex-col items-stretch gap-2">
            <div className="text-right text-xs uppercase tracking-[0.18em] text-slate-500">Gallery density</div>
            <DensityToggle density={density} onChange={setDensity} />
          </div>
        </div>
      </header>

      <div className="grid flex-1 items-start gap-6 xl:grid-cols-[340px_minmax(0,1fr)] 2xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="space-y-4 xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto xl:pr-2">
          <section className="card p-4">
            <button
              type="button"
              className="collapse-toggle"
              onClick={() => setSessionSummaryCollapsed((current) => !current)}
            >
              <div className="min-w-0 flex-1">
                <h2 className="panel-title text-sm font-semibold">Session</h2>
                <p className="mt-1 text-sm text-slate-400">
                  Active dataset, current view, and page status.
                </p>
              </div>
              <ChevronButton collapsed={sessionSummaryCollapsed} />
            </button>
            {!sessionSummaryCollapsed ? (
              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/80 p-3">
                <dl className="space-y-2 text-sm">
                  <CompactStatRow
                    label="Dataset"
                    value={activeDataset ? activeDataset.name : "Select a dataset"}
                    accentClassName="text-cyan-200"
                  />
                  <CompactStatRow
                    label="View"
                    value={activeSavedView ? activeSavedView.name : hasActiveViewFilters ? "Custom filtered view" : "Full dataset view"}
                  />
                  <CompactStatRow label="Status" value={currentViewStatusLabel} accentClassName="text-emerald-200" />
                </dl>
              </div>
            ) : null}
          </section>
          <CurrentViewPanel
            title={currentViewTitle}
            datasetName={activeDataset?.name ?? null}
            savedViewName={activeSavedView?.name ?? null}
            summaryParts={currentViewSummary}
            imageCount={view?.total ?? 0}
            annotationCount={view?.total_annotations ?? 0}
            statusLabel={currentViewStatusLabel}
            avgWidth={currentViewMetrics.avgWidth}
            avgHeight={currentViewMetrics.avgHeight}
            avgAspectRatio={currentViewMetrics.avgAspectRatio}
            embeddingSelectionCount={embeddingSelection.length}
            collapsed={currentViewCollapsed}
            onToggle={() => setCurrentViewCollapsed((current) => !current)}
            onClearEmbeddingFocus={clearEmbeddingFocus}
            onResetToFullDatasetView={resetToFullDatasetView}
            onSaveCurrentView={saveCurrentView}
            onUpdateSavedView={activeSavedView ? updateCurrentSavedView : undefined}
          />
          <section className="card p-4">
            {datasetsLoading && datasets.length === 0 ? (
              <div className="mb-3">
                <div className="mb-1 text-sm text-slate-300">Ingesting dataset, waiting for first records...</div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                  <div className="h-full w-1/3 animate-pulse rounded-full bg-cyan-400" />
                </div>
              </div>
            ) : null}
            <button
              type="button"
              className="collapse-toggle"
              onClick={() => setMissionControlsCollapsed((current) => !current)}
            >
              <div className="min-w-0 flex-1">
                <h2 className="panel-title text-sm font-semibold">Mission Controls</h2>
                <p className="mt-1 text-sm text-slate-400">
                  Server-backed dataset, view, and embedding controls.
                </p>
              </div>
              <ChevronButton collapsed={missionControlsCollapsed} />
            </button>
            {!missionControlsCollapsed ? (
              <div className="mt-4 space-y-3">
                <select
                  className="input-surface w-full px-3 py-2"
                  value={datasetId}
                  onChange={(e) => setDatasetId(e.target.value)}
                >
                  <option value="">Select dataset</option>
                  {datasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.image_count} imgs / {d.annotation_count} anns)
                    </option>
                  ))}
                </select>
                <select
                  className="input-surface w-full px-3 py-2"
                  value={groupBy}
                  onChange={(e) => setGroupBy(e.target.value as GroupByValue)}
                >
                  <option value="directory">Group: directory</option>
                  <option value="class">Group: class</option>
                  <option value="image_size_bucket">Group: image size</option>
                </select>
                <select
                  className="input-surface w-full px-3 py-2"
                  value={selectedSavedViewId}
                  onChange={(e) => {
                    const nextId = e.target.value;
                    if (!nextId) {
                      setSelectedSavedViewId("");
                      return;
                    }
                    loadSavedView(nextId);
                  }}
                  disabled={!datasetId || savedViewsLoading}
                >
                  <option value="">{savedViewsLoading ? "Loading saved views..." : "Custom / unsaved view"}</option>
                  {savedViews.map((savedView) => (
                    <option key={savedView.id} value={savedView.id}>
                      {savedView.name}
                    </option>
                  ))}
                </select>
                <button className="action-button w-full px-3 py-2 font-medium" onClick={() => void loadView()}>
                  Reload Current View
                </button>
                <div className="grid grid-cols-1 gap-2">
                  <button className="action-button-secondary px-3 py-2 text-sm font-medium" onClick={saveCurrentView}>
                    Save Current View
                  </button>
                  {activeSavedView ? (
                    <>
                      <button className="action-button-secondary px-3 py-2 text-sm font-medium" onClick={renameSavedView}>
                        Rename Saved View
                      </button>
                      <button className="action-button-secondary px-3 py-2 text-sm font-medium" onClick={deleteActiveSavedView}>
                        Delete Saved View
                      </button>
                    </>
                  ) : null}
                </div>
              </div>
            ) : null}
          </section>

          <section className="card p-4">
            <button
              type="button"
              className="collapse-toggle"
              onClick={() => setFiltersCollapsed((current) => !current)}
            >
              <div className="min-w-0 flex-1">
                <h2 className="panel-title text-sm font-semibold">Filters</h2>
                <p className="mt-1 text-sm text-slate-400">Directory, class, and box-size constraints that define the current dataset view.</p>
              </div>
              <ChevronButton collapsed={filtersCollapsed} />
            </button>
            {!filtersCollapsed ? (
              <div className="mt-4 space-y-3">
                <FilterBlock
                  title="Image Directory"
                  summary={directoryFilterSummary}
                  collapsed={directoryFilterCollapsed}
                  onToggle={() => setDirectoryFilterCollapsed((current) => !current)}
                >
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">
                      Select one or more latest-directory names. Leave none selected to include every directory.
                    </p>
                    <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                      <label
                        className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 transition ${
                          directoryFilter.length === 0
                            ? "border-cyan-400/45 bg-cyan-400/10 text-slate-100"
                            : "border-slate-800 bg-slate-950/80 text-slate-300 hover:border-slate-700"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="sr-only"
                          checked={directoryFilter.length === 0}
                          onChange={() => setDirectoryFilter([])}
                        />
                        <span
                          aria-hidden="true"
                          className={`flex h-5 w-5 items-center justify-center rounded-md border text-[11px] font-bold ${
                            directoryFilter.length === 0
                              ? "border-cyan-300 bg-cyan-400/90 text-slate-950"
                              : "border-slate-700 bg-slate-900 text-transparent"
                          }`}
                        >
                          ✓
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">All directories</span>
                          <span className="block text-xs uppercase tracking-[0.18em] text-slate-500">
                            Show every directory
                          </span>
                        </span>
                      </label>
                      {directoryOptions.map(([directoryName, count]) => {
                        const selected = directoryFilter.includes(directoryName);
                        return (
                          <label
                            key={directoryName}
                            className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 transition ${
                              selected
                                ? "border-cyan-400/45 bg-cyan-400/10 text-slate-100"
                                : "border-slate-800 bg-slate-950/80 text-slate-300 hover:border-slate-700"
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="sr-only"
                              checked={selected}
                              onChange={() => toggleDirectoryFilter(directoryName)}
                            />
                            <span
                              aria-hidden="true"
                              className={`flex h-5 w-5 items-center justify-center rounded-md border text-[11px] font-bold ${
                                selected
                                  ? "border-cyan-300 bg-cyan-400/90 text-slate-950"
                                  : "border-slate-700 bg-slate-900 text-transparent"
                              }`}
                            >
                              ✓
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium">
                                {directoryName} <span className="text-slate-500">({count})</span>
                              </span>
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                </FilterBlock>
                <FilterBlock
                  title="Class Filter"
                  summary={classFilterSummary}
                  collapsed={classFilterCollapsed}
                  onToggle={() => setClassFilterCollapsed((current) => !current)}
                >
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">
                      Select one or more class boxes. Leave none selected to keep every class visible.
                    </p>
                    <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                      <label
                        className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 transition ${
                          classFilter.length === 0
                            ? "border-cyan-400/45 bg-cyan-400/10 text-slate-100"
                            : "border-slate-800 bg-slate-950/80 text-slate-300 hover:border-slate-700"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="sr-only"
                          checked={classFilter.length === 0}
                          onChange={() => setClassFilter([])}
                        />
                        <span
                          aria-hidden="true"
                          className={`flex h-5 w-5 items-center justify-center rounded-md border text-[11px] font-bold ${
                            classFilter.length === 0
                              ? "border-cyan-300 bg-cyan-400/90 text-slate-950"
                              : "border-slate-700 bg-slate-900 text-transparent"
                          }`}
                        >
                          ✓
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">All classes</span>
                          <span className="block text-xs uppercase tracking-[0.18em] text-slate-500">
                            Show every class
                          </span>
                        </span>
                      </label>
                      {classOptions.map(([className, count]) => {
                        const selected = classFilter.includes(className);
                        return (
                          <label
                            key={className}
                            className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 transition ${
                              selected
                                ? "border-cyan-400/45 bg-cyan-400/10 text-slate-100"
                                : "border-slate-800 bg-slate-950/80 text-slate-300 hover:border-slate-700"
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="sr-only"
                              checked={selected}
                              onChange={() => toggleClassFilter(className)}
                            />
                            <span
                              aria-hidden="true"
                              className={`flex h-5 w-5 items-center justify-center rounded-md border text-[11px] font-bold ${
                                selected
                                  ? "border-cyan-300 bg-cyan-400/90 text-slate-950"
                                  : "border-slate-700 bg-slate-900 text-transparent"
                              }`}
                            >
                              ✓
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium">
                                {className} <span className="text-slate-500">({count})</span>
                              </span>
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                </FilterBlock>
                <FilterBlock
                  title="Bounding Box Size"
                  summary={bboxFilterSummary}
                  collapsed={bboxFiltersCollapsed}
                  onToggle={() => setBboxFiltersCollapsed((current) => !current)}
                >
                  <div className="space-y-4">
                    <p className="text-xs text-slate-500">
                      Width and height ranges are always available. Leave both sliders at their full span to include every box.
                    </p>
                    <RangeFilterControl title="Width" range={bboxWidthRange} limit={bboxWidthLimit} onChange={setBboxWidthRange} />
                    <RangeFilterControl
                      title="Height"
                      range={bboxHeightRange}
                      limit={bboxHeightLimit}
                      onChange={setBboxHeightRange}
                    />
                  </div>
                </FilterBlock>
              </div>
            ) : null}
          </section>

          <section className="card p-4">
            <button
              type="button"
              className="collapse-toggle"
              onClick={() => setActionsCollapsed((current) => !current)}
            >
              <div className="min-w-0 flex-1">
                <h2 className="panel-title text-sm font-semibold">Actions</h2>
                <p className="mt-1 text-sm text-slate-400">
                  {view
                    ? embeddingSelection.length > 0
                      ? `${embeddingSelection.length} images focused inside current view`
                      : isViewUpdating
                        ? "Updating server-backed view..."
                        : `${view.total} images / ${view.total_annotations} annotations in view`
                    : "Live sync every 5s"}
                </p>
              </div>
              <ChevronButton collapsed={actionsCollapsed} />
            </button>
            {!actionsCollapsed ? (
              <>
                <div className="mt-4 flex flex-col gap-2">
                  <button
                    className="action-button-secondary px-3 py-2 text-sm font-medium disabled:opacity-50"
                    onClick={runEmbeddings}
                    disabled={isEmbeddingsRunning}
                  >
                    {isEmbeddingsRunning ? "Computing Embeddings..." : "Compute View Embeddings"}
                  </button>
                  <button className="action-button px-3 py-2 text-sm font-medium" onClick={exportCurrentView}>
                    Export Current View (COCO)
                  </button>
                </div>
                {embeddingTaskStatus ? (
                  <EmbeddingTaskProgress
                    state={embeddingTaskStatus.state}
                    progress={embeddingTaskStatus.progress}
                    completed={embeddingTaskStatus.completed}
                    total={embeddingTaskStatus.total}
                    message={embeddingTaskStatus.message}
                  />
                ) : null}
                {message ? <p className="mt-3 text-sm text-cyan-200">{message}</p> : null}
                {activeDataset ? (
                  <p className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-500">Active dataset: {activeDataset.name}</p>
                ) : null}
              </>
            ) : null}
          </section>
        </aside>

        <div className="min-w-0 space-y-4">
          <section>
            <StatsPanels
              view={view}
              selectedClasses={classFilter}
              onClassToggle={toggleClassFilter}
              onClearClassSelection={() => setClassFilter([])}
              embedded
              showImageMetrics={false}
            />
          </section>
          <section>
            {projection.length > 0 ? (
              <EmbeddingMap
                points={projection}
                images={view?.images ?? []}
                selectedEntityIds={embeddingSelection}
                onSelectionChange={setEmbeddingSelection}
              />
            ) : null}
          </section>

          <section>
            <Board
              view={boardView}
              loading={loading}
              density={density}
              loadingMore={loadingMore}
              onLoadMore={() => void loadMoreImages()}
            />
          </section>
        </div>
      </div>
    </main>
  );
}

function DensityToggle({
  density,
  onChange
}: {
  density: GalleryDensity;
  onChange: (density: GalleryDensity) => void;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-1">
      <div className="grid grid-cols-2 gap-1">
        <button
          type="button"
          className={`rounded-xl px-3 py-2 text-xs font-medium uppercase tracking-[0.18em] ${
            density === "compact" ? "bg-cyan-500/15 text-cyan-200" : "text-slate-500"
          }`}
          onClick={() => onChange("compact")}
        >
          Dense Grid
        </button>
        <button
          type="button"
          className={`rounded-xl px-3 py-2 text-xs font-medium uppercase tracking-[0.18em] ${
            density === "comfortable" ? "bg-emerald-500/15 text-emerald-200" : "text-slate-500"
          }`}
          onClick={() => onChange("comfortable")}
        >
          Large Viewer
        </button>
      </div>
    </div>
  );
}

function CurrentViewPanel({
  title,
  datasetName,
  savedViewName,
  summaryParts,
  imageCount,
  annotationCount,
  statusLabel,
  avgWidth,
  avgHeight,
  avgAspectRatio,
  embeddingSelectionCount,
  collapsed,
  onToggle,
  onClearEmbeddingFocus,
  onResetToFullDatasetView,
  onSaveCurrentView,
  onUpdateSavedView
}: {
  title: string;
  datasetName: string | null;
  savedViewName: string | null;
  summaryParts: string[];
  imageCount: number;
  annotationCount: number;
  statusLabel: string;
  avgWidth: number;
  avgHeight: number;
  avgAspectRatio: number;
  embeddingSelectionCount: number;
  collapsed: boolean;
  onToggle: () => void;
  onClearEmbeddingFocus: () => void;
  onResetToFullDatasetView: () => void;
  onSaveCurrentView: () => void;
  onUpdateSavedView?: () => void;
}) {
  return (
    <section className="card p-4">
      <button
        type="button"
        className="collapse-toggle"
        onClick={onToggle}
      >
        <div className="min-w-0 flex-1">
          <h2 className="panel-title text-sm font-semibold">Current View</h2>
          <p className="mt-1 text-sm text-slate-400">
            Counts, view metadata, and quick actions.
          </p>
        </div>
        <ChevronButton collapsed={collapsed} />
      </button>
      {!collapsed ? (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.2em] text-emerald-200">
              {title}
            </span>
            {datasetName ? (
              <span className="rounded-full border border-slate-700 bg-slate-900/80 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                {datasetName}
              </span>
            ) : null}
            {savedViewName ? (
              <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-cyan-200">
                Saved: {savedViewName}
              </span>
            ) : null}
            {statusLabel === "Loading view" ? (
              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-amber-200">
                Updating View
              </span>
            ) : null}
            {embeddingSelectionCount > 0 ? (
              <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-cyan-200">
                Gallery focus: {embeddingSelectionCount} selected
              </span>
            ) : null}
          </div>
          {summaryParts.length > 0 ? (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {summaryParts.map((part) => (
                <span
                  key={part}
                  className="rounded-full border border-slate-700 bg-slate-900/80 px-2.5 py-0.5 text-[11px] text-slate-300"
                >
                  {part}
                </span>
              ))}
            </div>
          ) : null}
          <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3">
            <dl className="space-y-2 text-sm">
              <CompactStatRow label="Images in view" value={String(imageCount)} accentClassName="text-slate-100" />
              <CompactStatRow label="Annotations" value={String(annotationCount)} accentClassName="text-cyan-200" />
              <CompactStatRow
                label="Gallery focus"
                value={embeddingSelectionCount > 0 ? String(embeddingSelectionCount) : "Off"}
                accentClassName="text-violet-200"
              />
              <CompactStatRow label="Status" value={statusLabel} accentClassName="text-emerald-200" />
              <CompactStatRow label="Avg width" value={avgWidth.toFixed(0)} />
              <CompactStatRow label="Avg height" value={avgHeight.toFixed(0)} />
              <CompactStatRow label="Aspect ratio" value={avgAspectRatio.toFixed(2)} />
            </dl>
          </div>
          <div className="flex flex-col gap-2">
            <button className="action-button-secondary px-3 py-2 text-sm font-medium" onClick={onSaveCurrentView}>
              Save Current View
            </button>
            {onUpdateSavedView ? (
              <button className="action-button-secondary px-3 py-2 text-sm font-medium" onClick={onUpdateSavedView}>
                Update Saved View
              </button>
            ) : null}
            <button className="action-button px-3 py-2 text-sm font-medium" onClick={onResetToFullDatasetView}>
              Reset to Full Dataset View
            </button>
            {embeddingSelectionCount > 0 ? (
              <button
                type="button"
                className="action-button-secondary px-3 py-2 text-sm font-medium"
                onClick={onClearEmbeddingFocus}
              >
                Clear Embedding Focus
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function CompactStatRow({
  label,
  value,
  accentClassName = "text-slate-200"
}: {
  label: string;
  value: string;
  accentClassName?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</dt>
      <dd className={`text-sm font-medium ${accentClassName}`}>{value}</dd>
    </div>
  );
}

function EmbeddingTaskProgress({
  state,
  progress,
  completed,
  total,
  message
}: {
  state: "queued" | "running" | "done" | "failed";
  progress: number;
  completed?: number | null;
  total?: number | null;
  message: string;
}) {
  const counts = embeddingCounts(completed, total, message);
  const fraction = counts ? counts.completed / counts.total : clampProgress(progress);
  const samplesRef = useRef<PaceSample[]>([]);
  const paceKeyRef = useRef("");
  const [now, setNow] = useState(() => Date.now());
  const paceKey = counts ? `${counts.total}:${counts.completed}` : "none";
  if (paceKey !== paceKeyRef.current) {
    paceKeyRef.current = paceKey;
    if (!counts || counts.completed <= 0) {
      samplesRef.current = [];
    } else {
      const last = samplesRef.current[samplesRef.current.length - 1];
      samplesRef.current =
        last && counts.completed > last.completed
          ? [...samplesRef.current, { at: Date.now(), completed: counts.completed }].slice(-40)
          : [{ at: Date.now(), completed: counts.completed }];
    }
  }
  useEffect(() => {
    if (state !== "running") {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [state]);
  const progressBarColor =
    state === "failed"
      ? "bg-rose-500"
      : state === "done"
        ? "bg-emerald-500"
        : "bg-cyan-400";
  const label = counts
    ? `${counts.completed.toLocaleString()} / ${counts.total.toLocaleString()}`
    : `${Math.round(clampProgress(progress) * 100)}%`;
  const etaLabel =
    state === "running" && counts
      ? formatTimeLeft(estimateSecondsLeft(samplesRef.current, counts.total, now), counts.completed, counts.total)
      : null;

  return (
    <div className="mt-3 rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="panel-title text-sm font-semibold">Embedding Job</p>
        <div className="text-right">
          <span className="font-mono text-sm tabular-nums text-slate-200">{label}</span>
          {etaLabel ? <p className="mt-1 text-xs tabular-nums text-slate-400">{etaLabel}</p> : null}
        </div>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full transition-[width] duration-300 ${progressBarColor}`}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
      <p className="mt-2 text-sm text-slate-300">{message || "Working..."}</p>
    </div>
  );
}

type PaceSample = { at: number; completed: number };

function estimateSecondsLeft(samples: PaceSample[], total: number, now: number): number | null {
  const measured = samples.filter((sample) => sample.completed > 0);
  if (measured.length < 2) {
    return null;
  }
  const latest = measured[measured.length - 1];
  const recent = measured.filter((sample) => latest.at - sample.at <= 30_000 && latest.at - sample.at > 0);
  const earlier = recent.length > 0 ? recent[0] : measured[0];
  if (latest.completed <= earlier.completed || latest.at <= earlier.at) {
    return null;
  }
  const imagesPerSecond = (latest.completed - earlier.completed) / ((latest.at - earlier.at) / 1000);
  if (imagesPerSecond <= 0) {
    return null;
  }
  const remainingImages = Math.max(0, total - latest.completed);
  return remainingImages / imagesPerSecond - (now - latest.at) / 1000;
}

function formatTimeLeft(seconds: number | null, completed: number, total: number): string {
  if (completed >= total) {
    return "Finishing…";
  }
  if (seconds === null) {
    return "Estimating time left…";
  }
  if (seconds < 5) {
    return "Less than a minute left";
  }
  const remaining = Math.round(seconds);
  if (remaining < 60) {
    return `About ${remaining}s left`;
  }
  const minutes = Math.round(remaining / 60);
  if (minutes < 60) {
    return minutes === 1 ? "About 1 min left" : `About ${minutes} min left`;
  }
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (restMinutes === 0) {
    return hours === 1 ? "About 1 h left" : `About ${hours} h left`;
  }
  return `About ${hours} h ${restMinutes} min left`;
}

function embeddingCounts(
  completed: number | null | undefined,
  total: number | null | undefined,
  message: string
): { completed: number; total: number } | null {
  if (typeof completed === "number" && typeof total === "number" && total > 0) {
    return { completed, total };
  }
  const match = message.match(/(\d[\d,]*)\s+of\s+(\d[\d,]*)/);
  if (!match) {
    return null;
  }
  const parsedCompleted = Number(match[1].replaceAll(",", ""));
  const parsedTotal = Number(match[2].replaceAll(",", ""));
  if (!Number.isFinite(parsedCompleted) || !Number.isFinite(parsedTotal) || parsedTotal <= 0) {
    return null;
  }
  return { completed: parsedCompleted, total: parsedTotal };
}

function clampProgress(progress: number): number {
  if (!Number.isFinite(progress)) {
    return 0;
  }
  return Math.min(1, Math.max(0, progress));
}

function FilterBlock({
  title,
  summary,
  collapsed,
  onToggle,
  children
}: {
  title: string;
  summary: string;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
      <button type="button" className="collapse-toggle" onClick={onToggle}>
        <div className="min-w-0 flex-1">
          <p className="panel-title text-sm font-semibold">{title}</p>
          <p className="mt-1 truncate text-xs text-slate-500">{summary}</p>
        </div>
        <ChevronButton collapsed={collapsed} />
      </button>
      {!collapsed ? <div className="mt-4">{children}</div> : null}
    </div>
  );
}

function ChevronButton({ collapsed }: { collapsed: boolean }) {
  return (
    <span
      className={`collapse-chevron ${collapsed ? "" : "rotate-90"}`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 20 20" className="h-4 w-4 fill-current">
        <path d="M7.2 4.4 12.8 10l-5.6 5.6-1.4-1.4L10 10 5.8 5.8z" />
      </svg>
    </span>
  );
}

function RangeFilterControl({
  title,
  range,
  limit,
  onChange
}: {
  title: string;
  range: RangeFilterState;
  limit: number;
  onChange: (range: RangeFilterState) => void;
}) {
  const safeLimit = Math.max(1, limit);
  const minPercent = (range.min / safeLimit) * 100;
  const maxPercent = (range.max / safeLimit) * 100;

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
      <div className="mb-3">
        <p className="panel-title text-sm font-semibold">{title}</p>
        <p className="mt-1 text-xs text-slate-500">Use one dual-handle range to constrain minimum and maximum side length.</p>
      </div>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3 text-xs uppercase tracking-[0.18em] text-slate-500">
          <div>Min {range.min}px</div>
          <div className="text-right">Max {range.max}px</div>
        </div>
        <div className="range-slider">
          <div className="range-slider__track" />
          <div
            className="range-slider__active"
            style={{
              left: `${minPercent}%`,
              width: `${Math.max(maxPercent - minPercent, 0)}%`
            }}
          />
          <input
            className="range-slider__input"
            type="range"
            min={0}
            max={safeLimit}
            step={1}
            value={range.min}
            onChange={(e) =>
              onChange({
                min: Math.min(Number(e.target.value), range.max),
                max: range.max
              })
            }
          />
          <input
            className="range-slider__input"
            type="range"
            min={0}
            max={safeLimit}
            step={1}
            value={range.max}
            onChange={(e) =>
              onChange({
                min: range.min,
                max: Math.max(Number(e.target.value), range.min)
              })
            }
          />
        </div>
      </div>
    </div>
  );
}

function clampRange(range: RangeFilterState, limit: number): RangeFilterState {
  const safeLimit = Math.max(1, limit);
  const min = Math.max(0, Math.min(range.min, safeLimit));
  const max = Math.max(min, Math.min(range.max || safeLimit, safeLimit));
  return { min, max };
}

function buildCurrentFilters(
  directoryFilter: string[],
  classFilter: string[],
  bboxWidthRange: RangeFilterState,
  bboxWidthLimit: number,
  bboxHeightRange: RangeFilterState,
  bboxHeightLimit: number
): ViewFilter[] {
  const nextFilters: ViewFilter[] = [];
  if (directoryFilter.length === 1) {
    nextFilters.push({ field: "directory", operator: "eq", value: directoryFilter[0] });
  } else if (directoryFilter.length > 1) {
    nextFilters.push({ field: "directory", operator: "in", value: directoryFilter });
  }
  if (classFilter.length === 1) {
    nextFilters.push({ field: "class", operator: "eq", value: classFilter[0] });
  } else if (classFilter.length > 1) {
    nextFilters.push({ field: "class", operator: "in", value: classFilter });
  }
  if (!isFullRange(bboxWidthRange, bboxWidthLimit)) {
    nextFilters.push({ field: "bbox_width", operator: "gte", value: bboxWidthRange.min });
    nextFilters.push({ field: "bbox_width", operator: "lte", value: bboxWidthRange.max });
  }
  if (!isFullRange(bboxHeightRange, bboxHeightLimit)) {
    nextFilters.push({ field: "bbox_height", operator: "gte", value: bboxHeightRange.min });
    nextFilters.push({ field: "bbox_height", operator: "lte", value: bboxHeightRange.max });
  }
  return nextFilters;
}

function extractDirectoryFilter(filters: ViewFilter[]): string[] {
  const directoryFilter = filters.find((filter) => filter.field === "directory");
  if (!directoryFilter) {
    return [];
  }
  if (directoryFilter.operator === "eq" && typeof directoryFilter.value === "string") {
    return [directoryFilter.value];
  }
  if (directoryFilter.operator === "in" && Array.isArray(directoryFilter.value)) {
    return directoryFilter.value.filter((value): value is string => typeof value === "string");
  }
  return [];
}

function extractClassFilter(filters: ViewFilter[]): string[] {
  const classFilter = filters.find((filter) => filter.field === "class");
  if (!classFilter) {
    return [];
  }
  if (classFilter.operator === "eq" && typeof classFilter.value === "string") {
    return [classFilter.value];
  }
  if (classFilter.operator === "in" && Array.isArray(classFilter.value)) {
    return classFilter.value.filter((value): value is string => typeof value === "string");
  }
  return [];
}

function extractRangeFromFilters(filters: ViewFilter[], field: "bbox_width" | "bbox_height", limit: number): RangeFilterState {
  let min = 0;
  let max = Math.max(1, limit);
  for (const filter of filters) {
    if (filter.field !== field || typeof filter.value !== "number") {
      continue;
    }
    if (filter.operator === "gte") {
      min = filter.value;
    } else if (filter.operator === "lte") {
      max = filter.value;
    }
  }
  return clampRange({ min, max }, limit);
}

function areViewSpecsEqual(left: ViewSpec, right: ViewSpec): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function appendGalleryPage(current: ViewResult, next: ViewResult): ViewResult {
  const imageIds = new Set(current.images.map((image) => image.id));
  const annotationIds = new Set(current.annotations.map((annotation) => annotation.id));
  return {
    ...current,
    total: next.total,
    total_annotations: next.total_annotations,
    class_distribution: next.class_distribution,
    groups: next.groups,
    avg_width: next.avg_width ?? current.avg_width,
    avg_height: next.avg_height ?? current.avg_height,
    avg_aspect_ratio: next.avg_aspect_ratio ?? current.avg_aspect_ratio,
    images: current.images.concat(next.images.filter((image) => !imageIds.has(image.id))),
    annotations: current.annotations.concat(
      next.annotations.filter((annotation) => !annotationIds.has(annotation.id))
    )
  };
}

function appendFocusedImages(current: ViewResult, next: ViewResult): ViewResult {
  const imageIds = new Set(current.images.map((image) => image.id));
  const annotationIds = new Set(current.annotations.map((annotation) => annotation.id));
  const images = next.images.filter((image) => !imageIds.has(image.id));
  const annotations = next.annotations.filter((annotation) => !annotationIds.has(annotation.id));
  if (images.length === 0 && annotations.length === 0) {
    return current;
  }
  return {
    ...current,
    images: current.images.concat(images),
    annotations: current.annotations.concat(annotations)
  };
}

function buildEmbeddingRequest(datasetId: string, spec: ViewSpec, savedViewId: string | null) {
  return savedViewId
    ? {
        dataset_id: datasetId,
        model: { provider: "hf", model_id: "openai/clip-vit-base-patch32", mode: "image", batch_size: 32 },
        saved_view_id: savedViewId
      }
    : {
        dataset_id: datasetId,
        model: { provider: "hf", model_id: "openai/clip-vit-base-patch32", mode: "image", batch_size: 32 },
        view: spec
      };
}

function buildExportRequest(spec: ViewSpec, savedViewId: string | null): ViewQueryRequest | ViewSpec {
  if (savedViewId) {
    return { saved_view_id: savedViewId };
  }
  return spec;
}

function extractRunId(result: Record<string, unknown> | null | undefined): string | null {
  if (!result || typeof result !== "object") {
    return null;
  }
  const id = result.id;
  return typeof id === "string" ? id : null;
}

function extractImageCount(result: Record<string, unknown> | null | undefined): number | null {
  if (!result || typeof result !== "object") {
    return null;
  }
  const config = result.config;
  if (config && typeof config === "object" && typeof (config as { image_count?: unknown }).image_count === "number") {
    return (config as { image_count: number }).image_count;
  }
  return null;
}

function isGroupByValue(value: string | null | undefined): value is GroupByValue {
  return value === "directory" || value === "class" || value === "image_size_bucket";
}

function formatClassFilterSummary(selectedClasses: string[]): string {
  if (selectedClasses.length === 0) {
    return "All classes";
  }
  if (selectedClasses.length <= 2) {
    return selectedClasses.join(", ");
  }
  return `${selectedClasses.length} classes selected`;
}

function formatDirectoryFilterSummary(selectedDirectories: string[]): string {
  if (selectedDirectories.length === 0) {
    return "All directories";
  }
  if (selectedDirectories.length <= 2) {
    return selectedDirectories.join(", ");
  }
  return `${selectedDirectories.length} directories selected`;
}

function formatBboxFilterSummary(
  bboxWidthRange: RangeFilterState,
  bboxWidthLimit: number,
  bboxHeightRange: RangeFilterState,
  bboxHeightLimit: number
): string {
  const widthFull = isFullRange(bboxWidthRange, bboxWidthLimit);
  const heightFull = isFullRange(bboxHeightRange, bboxHeightLimit);

  if (widthFull && heightFull) {
    return "Full width and height range";
  }

  const parts = [];
  if (!widthFull) {
    parts.push(`W ${bboxWidthRange.min}-${bboxWidthRange.max}px`);
  }
  if (!heightFull) {
    parts.push(`H ${bboxHeightRange.min}-${bboxHeightRange.max}px`);
  }
  return parts.join(" | ");
}

function isFullRange(range: RangeFilterState, limit: number): boolean {
  const safeLimit = Math.max(1, limit);
  return range.min <= 0 && range.max >= safeLimit;
}

function buildClassDistribution(annotations: ViewResult["annotations"]): Record<string, number> {
  return Object.fromEntries(
    Object.entries(
      annotations.reduce<Record<string, number>>((accumulator, annotation) => {
        accumulator[annotation.class_name] = (accumulator[annotation.class_name] ?? 0) + 1;
        return accumulator;
      }, {})
    ).sort(([leftClass, leftCount], [rightClass, rightCount]) => rightCount - leftCount || leftClass.localeCompare(rightClass))
  );
}

function buildGroups(
  images: ViewResult["images"],
  annotations: ViewResult["annotations"],
  groupBy: "directory" | "class" | "image_size_bucket"
): ViewResult["groups"] {
  if (groupBy === "directory") {
    return toSortedGroups(
      images.reduce<Record<string, number>>((accumulator, image) => {
        accumulator[image.directory_name] = (accumulator[image.directory_name] ?? 0) + 1;
        return accumulator;
      }, {})
    );
  }

  if (groupBy === "class") {
    return toSortedGroups(buildClassDistribution(annotations));
  }

  return toSortedGroups(
    images.reduce<Record<string, number>>((accumulator, image) => {
      const area = image.width * image.height;
      const key = area < 512 * 512 ? "small" : area < 1280 * 720 ? "medium" : "large";
      accumulator[key] = (accumulator[key] ?? 0) + 1;
      return accumulator;
    }, {})
  );
}

function toSortedGroups(counts: Record<string, number>): ViewResult["groups"] {
  return Object.entries(counts)
    .sort(([leftKey], [rightKey]) => leftKey.localeCompare(rightKey))
    .map(([key, count]) => ({ key, count }));
}

function filterViewToImageIds(view: ViewResult | null, imageIds: Set<number>): ViewResult | null {
  if (!view) {
    return null;
  }

  const images = view.images.filter((image) => imageIds.has(image.id));
  const annotations = view.annotations.filter((annotation) => imageIds.has(annotation.image_id));
  const classDistribution = Object.fromEntries(
    Object.entries(
      annotations.reduce<Record<string, number>>((accumulator, annotation) => {
        accumulator[annotation.class_name] = (accumulator[annotation.class_name] ?? 0) + 1;
        return accumulator;
      }, {})
    ).sort(([leftClass, leftCount], [rightClass, rightCount]) => rightCount - leftCount || leftClass.localeCompare(rightClass))
  );
  const groups =
    view.groups.length > 0
      ? view.groups.filter((group) =>
          images.some((image) => {
            if (group.key === image.directory_name) {
              return true;
            }
            return annotations.some((annotation) => annotation.image_id === image.id && annotation.class_name === group.key);
          })
        )
      : [];

  return {
    ...view,
    total: images.length,
    total_annotations: annotations.length,
    class_distribution: classDistribution,
    groups,
    images,
    annotations
  };
}
