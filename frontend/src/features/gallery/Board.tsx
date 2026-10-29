"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type ViewResult } from "@/lib/api";

type Props = {
  view: ViewResult | null;
  loading: boolean;
  density: GalleryDensity;
  loadingMore?: boolean;
  onLoadMore?: () => void;
};

type ViewImage = ViewResult["images"][number];
type ViewAnnotation = ViewResult["annotations"][number];
export type GalleryDensity = "compact" | "comfortable";
const INITIAL_RENDER_COUNT: Record<GalleryDensity, number> = {
  compact: 120,
  comfortable: 60
};

export function Board({ view, loading, density, loadingMore = false, onLoadMore }: Props) {
  const [selectedImageId, setSelectedImageId] = useState<number | null>(null);
  const [renderCount, setRenderCount] = useState<number>(INITIAL_RENDER_COUNT[density]);

  useEffect(() => {
    setRenderCount(INITIAL_RENDER_COUNT[density]);
  }, [density, view?.total]);

  const visibleImages = useMemo(() => view?.images.slice(0, renderCount) ?? [], [renderCount, view?.images]);
  const visibleImageIds = useMemo(() => new Set<number>(visibleImages.map((image) => image.id)), [visibleImages]);

  const annotationsByImage = useMemo(() => {
    const map = new Map<number, ViewAnnotation[]>();
    if (!view) {
      return map;
    }
    for (const ann of view.annotations) {
      if (!visibleImageIds.has(ann.image_id)) {
        continue;
      }
      const curr = map.get(ann.image_id) ?? [];
      curr.push(ann);
      map.set(ann.image_id, curr);
    }
    return map;
  }, [view, visibleImageIds]);

  const selectedImage = useMemo(
    () => visibleImages.find((img) => img.id === selectedImageId) ?? null,
    [selectedImageId, visibleImages]
  );
  const selectedImageIndex = useMemo(
    () => (selectedImageId ? visibleImages.findIndex((img) => img.id === selectedImageId) : -1),
    [selectedImageId, visibleImages]
  );

  const selectedAnnotations = useMemo(
    () => (selectedImage ? annotationsByImage.get(selectedImage.id) ?? [] : []),
    [annotationsByImage, selectedImage]
  );
  const hasPreviousImage = selectedImageIndex > 0;
  const hasNextImage = selectedImageIndex >= 0 && selectedImageIndex < visibleImages.length - 1;
  const hasBufferedImages = view ? visibleImages.length < view.images.length : false;
  const hasRemoteImages = view ? view.images.length < view.total : false;
  const hasMoreImages = hasBufferedImages || (hasRemoteImages && Boolean(onLoadMore));

  function showPreviousImage() {
    if (!hasPreviousImage) {
      return;
    }
    setSelectedImageId(visibleImages[selectedImageIndex - 1].id);
  }

  function showNextImage() {
    if (!hasNextImage) {
      return;
    }
    setSelectedImageId(visibleImages[selectedImageIndex + 1].id);
  }

  useEffect(() => {
    if (!view || !selectedImageId) {
      return;
    }
    const imageStillVisible = visibleImages.some((img) => img.id === selectedImageId);
    if (!imageStillVisible) {
      setSelectedImageId(null);
    }
  }, [selectedImageId, view, visibleImages]);

  useEffect(() => {
    if (!selectedImage) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSelectedImageId(null);
      }
      if (event.key === "ArrowLeft") {
        showPreviousImage();
      }
      if (event.key === "ArrowRight") {
        showNextImage();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hasNextImage, hasPreviousImage, selectedImage, selectedImageIndex, view]);

  if (loading) {
    return (
      <div className="card p-4">
        <div className="mb-2 text-sm text-slate-300">Loading dataset view...</div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-cyan-400" />
        </div>
      </div>
    );
  }
  if (!view) {
    return <div className="card p-4 text-slate-300">No dataset selected yet.</div>;
  }
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="panel-title text-sm font-semibold">Image Field</h2>
          <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
            Rendering {visibleImages.length} of {view.total} images in this view
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-sm">
          {view.groups.map((g) => (
            <span
              key={g.key}
              className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 font-medium text-cyan-200"
            >
              {g.key} - {g.count}
            </span>
          ))}
        </div>
      </div>
      <div
        className={
          density === "compact"
            ? "grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5 2xl:grid-cols-6"
            : "grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"
        }
      >
        {visibleImages.map((img) => (
          <div key={img.id} className="card overflow-hidden p-2">
            <button type="button" className="block w-full text-left" onClick={() => setSelectedImageId(img.id)}>
              <AnnotatedImagePreview
                image={img}
                annotations={annotationsByImage.get(img.id) ?? []}
                density={density}
              />
            </button>
          </div>
        ))}
      </div>
      {hasMoreImages ? (
        <div className="card flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-sm text-slate-400">
            The full view contains {view.total} images. Showing {visibleImages.length} so the page stays small.
          </p>
          <button
            type="button"
            className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-200 disabled:opacity-50"
            disabled={loadingMore}
            onClick={() => {
              if (hasBufferedImages) {
                setRenderCount((current) => current + INITIAL_RENDER_COUNT[density]);
                return;
              }
              setRenderCount((current) => current + INITIAL_RENDER_COUNT[density]);
              onLoadMore?.();
            }}
          >
            {loadingMore
              ? "Loading..."
              : `Load ${
                  hasBufferedImages
                    ? Math.min(INITIAL_RENDER_COUNT[density], view.images.length - visibleImages.length)
                    : INITIAL_RENDER_COUNT[density]
                } More`}
          </button>
        </div>
      ) : null}
      {selectedImage ? (
        <ImageDetailModal
          image={selectedImage}
          annotations={selectedAnnotations}
          imageIndex={selectedImageIndex}
          imageCount={visibleImages.length}
          hasPreviousImage={hasPreviousImage}
          hasNextImage={hasNextImage}
          onPrevious={showPreviousImage}
          onNext={showNextImage}
          onClose={() => setSelectedImageId(null)}
        />
      ) : null}
    </div>
  );
}

function AnnotatedImagePreview({
  image,
  annotations,
  density
}: {
  image: ViewImage;
  annotations: ViewAnnotation[];
  density: GalleryDensity;
}) {
  const [loadFailed, setLoadFailed] = useState<boolean>(false);

  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-slate-800 bg-slate-950 transition hover:border-cyan-500/50 ${
        density === "compact" ? "min-h-[180px]" : "min-h-[260px]"
      }`}
      style={{ aspectRatio: `${image.width} / ${image.height}` }}
    >
      {!loadFailed ? (
        <>
          <img
            src={api.imageUrl(image.file_path)}
            alt={image.file_path}
            loading="lazy"
            className="absolute inset-0 h-full w-full object-contain"
            onError={() => setLoadFailed(true)}
          />
          <div className="pointer-events-none absolute inset-0">
            {annotations.map((ann) => {
              const [x, y, width, height] = ann.bbox_xywh;
              return (
                <div
                  key={ann.id}
                  className="absolute border border-cyan-400/90 shadow-[0_0_0_1px_rgba(2,6,23,0.75)]"
                  style={{
                    left: `${(x / image.width) * 100}%`,
                    top: `${(y / image.height) * 100}%`,
                    width: `${(width / image.width) * 100}%`,
                    height: `${(height / image.height) * 100}%`
                  }}
                >
                  {density === "comfortable" ? (
                    <div className="absolute left-0 top-0 rounded-br-md bg-cyan-400/90 px-1.5 py-0.5 text-[10px] font-semibold text-slate-950">
                      {ann.class_name}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <div className="flex h-full items-center justify-center text-xs uppercase tracking-[0.2em] text-slate-500">
          Preview unavailable
        </div>
      )}
    </div>
  );
}

function ImageDetailModal({
  image,
  annotations,
  imageIndex,
  imageCount,
  hasPreviousImage,
  hasNextImage,
  onPrevious,
  onNext,
  onClose
}: {
  image: ViewImage;
  annotations: ViewAnnotation[];
  imageIndex: number;
  imageCount: number;
  hasPreviousImage: boolean;
  hasNextImage: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onClose: () => void;
}) {
  const classGroups = useMemo(() => {
    const grouped = new Map<
      string,
      {
        count: number;
        annotations: ViewAnnotation[];
      }
    >();

    for (const ann of annotations) {
      const current = grouped.get(ann.class_name) ?? { count: 0, annotations: [] };
      current.count += 1;
      current.annotations.push(ann);
      grouped.set(ann.class_name, current);
    }

    return Array.from(grouped.entries())
      .map(([className, value]) => ({
        className,
        count: value.count,
        annotations: value.annotations
      }))
      .sort((left, right) => right.count - left.count || left.className.localeCompare(right.className));
  }, [annotations]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="h-[95vh] w-full max-w-[96vw] rounded-[28px] border border-slate-800 bg-slate-950/95 p-5 shadow-[0_30px_100px_rgba(2,6,23,0.75)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <p className="panel-title text-sm font-semibold">Image Inspection</p>
            <h3 className="mt-1 break-all font-mono text-sm text-slate-100">{image.file_path}</h3>
            <p className="mt-2 text-xs uppercase tracking-[0.2em] text-slate-500">
              Image {imageIndex + 1} of {imageCount} | {image.width}x{image.height} | {annotations.length} detections
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
              onClick={onPrevious}
              disabled={!hasPreviousImage}
            >
              Previous
            </button>
            <button
              type="button"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
              onClick={onNext}
              disabled={!hasNextImage}
            >
              Next
            </button>
            <button
              type="button"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200"
              onClick={onClose}
            >
              Close
            </button>
          </div>
        </div>
        <div className="grid h-[calc(95vh-7.5rem)] gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="relative flex min-h-0 items-center justify-center overflow-auto rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
            <button
              type="button"
              aria-label="Show previous image"
              className="absolute left-4 top-1/2 z-10 flex h-14 w-14 -translate-y-1/2 items-center justify-center rounded-full border border-slate-700/80 bg-slate-950/85 text-2xl text-slate-100 shadow-[0_18px_50px_rgba(2,6,23,0.55)] transition hover:border-cyan-400/50 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-30"
              onClick={onPrevious}
              disabled={!hasPreviousImage}
            >
              ‹
            </button>
            <button
              type="button"
              aria-label="Show next image"
              className="absolute right-4 top-1/2 z-10 flex h-14 w-14 -translate-y-1/2 items-center justify-center rounded-full border border-slate-700/80 bg-slate-950/85 text-2xl text-slate-100 shadow-[0_18px_50px_rgba(2,6,23,0.55)] transition hover:border-cyan-400/50 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-30"
              onClick={onNext}
              disabled={!hasNextImage}
            >
              ›
            </button>
            <div className="relative inline-block max-h-full max-w-full">
              <img
                src={api.imageUrl(image.file_path)}
                alt={image.file_path}
                className="block max-h-[82vh] max-w-full rounded-xl"
              />
              <div className="pointer-events-none absolute inset-0">
                {annotations.map((ann) => {
                  const [x, y, width, height] = ann.bbox_xywh;
                  return (
                    <div
                      key={ann.id}
                      className="absolute border-2 border-cyan-400 shadow-[0_0_0_1px_rgba(8,15,30,0.8)]"
                      style={{
                        left: `${(x / image.width) * 100}%`,
                        top: `${(y / image.height) * 100}%`,
                        width: `${(width / image.width) * 100}%`,
                        height: `${(height / image.height) * 100}%`
                      }}
                    >
                      <div className="absolute left-0 top-0 rounded-br-md bg-cyan-400/90 px-2 py-1 text-[11px] font-semibold text-slate-950">
                        {ann.class_name}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <div className="min-h-0 overflow-y-auto rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3">
              <h4 className="panel-title text-sm font-semibold">Image Details</h4>
              <dl className="mt-3 space-y-2 text-sm">
                <DetailRow label="File" value={image.file_path.split("/").pop() ?? image.file_path} />
                <DetailRow label="Directory" value={image.directory_name} />
                <DetailRow label="Dimensions" value={`${image.width}x${image.height}`} />
                <DetailRow label="Detections" value={String(annotations.length)} />
              </dl>
            </div>
            <h4 className="mt-4 panel-title text-sm font-semibold">Detected Classes</h4>
            <p className="mt-2 text-xs text-slate-500">Expand a class to inspect the exact bounding boxes for that label.</p>
            <div className="mt-3 space-y-3">
              {classGroups.length > 0 ? (
                classGroups.map((group) => (
                  <details
                    key={group.className}
                    className="rounded-xl border border-slate-800 bg-slate-900/80 p-3 text-sm"
                  >
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
                      <span className="font-medium text-cyan-200">{group.className}</span>
                      <span className="rounded-full border border-slate-700 bg-slate-950/80 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                        {group.count} instance{group.count === 1 ? "" : "s"}
                      </span>
                    </summary>
                    <div className="mt-3 space-y-2">
                      {group.annotations.map((ann, index) => {
                        const [x, y, width, height] = ann.bbox_xywh;
                        return (
                          <div key={ann.id} className="rounded-lg border border-slate-800 bg-slate-950/80 p-3">
                            <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                              Box {index + 1}
                            </div>
                            <div className="mt-1 font-mono text-[11px] text-slate-400">
                              bbox [{x.toFixed(1)}, {y.toFixed(1)}, {width.toFixed(1)}, {height.toFixed(1)}]
                            </div>
                            <div className="mt-1 text-xs text-slate-500">Area {ann.area.toFixed(1)}</div>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                ))
              ) : (
                <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3 text-sm text-slate-400">
                  No annotations for this image.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</dt>
      <dd className="max-w-[65%] break-all text-right text-sm text-slate-200">{value}</dd>
    </div>
  );
}
