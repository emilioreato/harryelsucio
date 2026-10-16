import { useCallback, useEffect, useRef, useState } from "react";
import { Maximize2, Minus, Plus } from "lucide-react";
import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";

const MIN_SCALE = 1;
const MAX_SCALE = 8;
const MOUSE_WHEEL_FACTOR = 1.18;
const TRACKPAD_SENSITIVITY = 0.0016;

function assignRef(ref, value) {
  if (typeof ref === "function") ref(value);
  else if (ref) ref.current = value;
}

function isInteractiveTarget(target) {
  return target instanceof Element
    && Boolean(target.closest("input, textarea, select, button, [contenteditable]:not([contenteditable='false']), [role='textbox']"));
}

function clampScale(scale) {
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));
}

export default function ZoomableImageViewport({
  src,
  alt = "",
  imageRef,
  surfaceRef,
  imageClassName = "",
  className = "",
  children,
  resetKey,
  allowLeftPan = true,
  allowDoubleClick = true,
  showCrosshair = false,
  suppressClickAfterDrag = false,
  onLoad,
  onError,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onClick,
}) {
  const frameRef = useRef(null);
  const internalImageRef = useRef(null);
  const controlsRef = useRef(null);
  const controlsHideTimerRef = useRef(0);
  const hasZoomedRef = useRef(false);
  const isAtFitScaleRef = useRef(true);
  const naturalSizeRef = useRef(null);
  const frameSizeRef = useRef(null);
  const lastResetKeyRef = useRef(resetKey);
  const navigationPointerRef = useRef(null);
  const middlePanRef = useRef(null);
  const activeToolPointersRef = useRef(new Set());
  const touchPointersRef = useRef(new Set());
  const touchPinchingRef = useRef(false);
  const pointerCandidateRef = useRef(null);
  const suppressPanClickRef = useRef(false);
  const suppressDragClickRef = useRef(false);
  const clearClickTimerRef = useRef(0);
  const [fitSize, setFitSize] = useState({ width: 0, height: 0 });
  const [scale, setScale] = useState(MIN_SCALE);
  const [showZoomControls, setShowZoomControls] = useState(true);
  const [spacePressed, setSpacePressed] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const canPanWithLeft = allowLeftPan || spacePressed;

  const measureFit = useCallback(() => {
    const frame = frameRef.current;
    const image = internalImageRef.current;
    if (!frame || !image?.naturalWidth || !image.naturalHeight) return;
    const availableWidth = frame.clientWidth;
    const availableHeight = frame.clientHeight;
    if (availableWidth <= 0 || availableHeight <= 0) return;

    const previousSize = frameSizeRef.current;
    const changedSignificantly = previousSize && (
      Math.abs(availableWidth - previousSize.width) >= Math.max(48, previousSize.width * 0.08)
      || Math.abs(availableHeight - previousSize.height) >= Math.max(48, previousSize.height * 0.08)
    );
    frameSizeRef.current = { width: availableWidth, height: availableHeight };

    const fit = Math.min(availableWidth / image.naturalWidth, availableHeight / image.naturalHeight);
    const next = {
      width: Math.max(1, image.naturalWidth * fit),
      height: Math.max(1, image.naturalHeight * fit),
    };
    setFitSize((current) => (
      Math.abs(current.width - next.width) < 0.5 && Math.abs(current.height - next.height) < 0.5
        ? current
        : next
    ));
    if (changedSignificantly) {
      window.requestAnimationFrame(() => controlsRef.current?.resetTransform(0));
    }
  }, []);

  const attachImageRef = useCallback((node) => {
    internalImageRef.current = node;
    assignRef(imageRef, node);
  }, [imageRef]);

  const attachSurfaceRef = useCallback((node) => {
    assignRef(surfaceRef, node);
  }, [surfaceRef]);

  const scheduleZoomControlsHide = useCallback(() => {
    if (!hasZoomedRef.current || !isAtFitScaleRef.current) return;
    window.clearTimeout(controlsHideTimerRef.current);
    controlsHideTimerRef.current = window.setTimeout(() => setShowZoomControls(false), 3000);
  }, []);

  const revealZoomControls = useCallback(() => {
    setShowZoomControls(true);
    if (isAtFitScaleRef.current) scheduleZoomControlsHide();
    else window.clearTimeout(controlsHideTimerRef.current);
  }, [scheduleZoomControlsHide]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return undefined;
    measureFit();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measureFit);
    observer?.observe(frame);
    window.addEventListener("resize", measureFit);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measureFit);
    };
  }, [measureFit]);

  useEffect(() => {
    let active = true;
    const setPressed = (pressed) => {
      if (!active) return;
      setSpacePressed(pressed);
    };
    const handleKeyDown = (event) => {
      if ((event.code !== "Space" && event.key !== " ") || isInteractiveTarget(event.target)) return;
      setPressed(true);
      event.preventDefault();
    };
    const handleKeyUp = (event) => {
      if (event.code === "Space" || event.key === " ") setPressed(false);
    };
    const handleBlur = () => {
      setPressed(false);
      navigationPointerRef.current = null;
      middlePanRef.current = null;
      activeToolPointersRef.current.forEach((pointerId) => onPointerCancel?.({ pointerId }));
      activeToolPointersRef.current.clear();
      touchPointersRef.current.clear();
      touchPinchingRef.current = false;
      pointerCandidateRef.current = null;
      suppressPanClickRef.current = false;
      suppressDragClickRef.current = false;
      setIsDragging(false);
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", handleBlur);
    return () => {
      active = false;
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", handleBlur);
    };
  }, [onPointerCancel]);

  useEffect(() => {
    if (Object.is(lastResetKeyRef.current, resetKey)) return;
    lastResetKeyRef.current = resetKey;
    controlsRef.current?.resetTransform(0);
    navigationPointerRef.current = null;
    middlePanRef.current = null;
    const wrapper = frameRef.current?.querySelector(".zoomable-viewport__clip");
    activeToolPointersRef.current.forEach((pointerId) => onPointerCancel?.({ pointerId }));
    activeToolPointersRef.current.forEach((pointerId) => {
      if (wrapper?.hasPointerCapture?.(pointerId)) wrapper.releasePointerCapture(pointerId);
    });
    activeToolPointersRef.current.clear();
    touchPointersRef.current.clear();
    touchPinchingRef.current = false;
    pointerCandidateRef.current = null;
    suppressPanClickRef.current = false;
    suppressDragClickRef.current = false;
    setSpacePressed(false);
    setIsDragging(false);
  }, [onPointerCancel, resetKey]);

  useEffect(() => () => {
    window.clearTimeout(clearClickTimerRef.current);
    window.clearTimeout(controlsHideTimerRef.current);
  }, []);

  const handleImageLoad = useCallback((event) => {
    const image = event.currentTarget;
    const previous = naturalSizeRef.current;
    const next = { width: image.naturalWidth, height: image.naturalHeight };
    const aspectChanged = previous
      && Math.abs(previous.width / previous.height - next.width / next.height) > 0.005;
    naturalSizeRef.current = next;
    measureFit();
    onLoad?.(event);
    if (aspectChanged) window.requestAnimationFrame(() => controlsRef.current?.resetTransform(0));
  }, [measureFit, onLoad]);

  const handleTransform = useCallback((_ref, nextState) => {
    isAtFitScaleRef.current = nextState.scale <= MIN_SCALE + 0.005;
    if (isAtFitScaleRef.current) {
      if (hasZoomedRef.current) {
        setShowZoomControls(true);
        scheduleZoomControlsHide();
      }
    } else {
      hasZoomedRef.current = true;
      window.clearTimeout(controlsHideTimerRef.current);
      setShowZoomControls(true);
    }
    setScale((current) => (Math.abs(current - nextState.scale) < 0.005 ? current : nextState.scale));
  }, [scheduleZoomControlsHide]);

  const clearClickSuppressionSoon = (delay = 500) => {
    window.clearTimeout(clearClickTimerRef.current);
    clearClickTimerRef.current = window.setTimeout(() => {
      suppressPanClickRef.current = false;
      suppressDragClickRef.current = false;
    }, delay);
  };

  const handlePanningStart = () => {
    suppressPanClickRef.current = false;
    setIsDragging(true);
  };
  const handlePanning = () => {
    suppressPanClickRef.current = true;
  };
  const handlePanningStop = () => {
    setIsDragging(false);
    clearClickSuppressionSoon();
  };

  const renderViewport = (controls) => {
    controlsRef.current = controls;
    const currentScale = scale;
    const leftPanEnabled = allowLeftPan || spacePressed;
    const wrapperClass = [
      "zoomable-viewport__clip",
      leftPanEnabled ? "can-pan" : "",
      showCrosshair ? "is-crosshair" : "",
      isDragging ? "is-dragging" : "",
      spacePressed && !allowLeftPan ? "is-space-panning" : "",
      className,
    ].filter(Boolean).join(" ");

    const handleWheel = (event) => {
      if (!event.deltaY) return;
      event.preventDefault();
      event.stopPropagation();
      const smoothTrackpad = event.ctrlKey || (event.deltaMode === 0 && Math.abs(event.deltaY) < 50);
      const factor = smoothTrackpad
        ? Math.exp(-event.deltaY * TRACKPAD_SENSITIVITY)
        : (event.deltaY < 0 ? MOUSE_WHEEL_FACTOR : 1 / MOUSE_WHEEL_FACTOR);
      const nextScale = clampScale(controls.instance.state.scale * factor);
      if (Math.abs(nextScale - controls.instance.state.scale) < 0.001) return;
      controls.zoomToPoint(nextScale, event.clientX, event.clientY, 0);
    };

    const handleViewportPointerDown = (event) => {
      if (event.pointerType === "touch") {
        const touchPointers = touchPointersRef.current;
        if (touchPointers.size > 0) {
          const firstPointerId = touchPointers.values().next().value;
          touchPointers.add(event.pointerId);
          if (!touchPinchingRef.current) {
            touchPinchingRef.current = true;
            activeToolPointersRef.current.delete(firstPointerId);
            onPointerCancel?.({ pointerId: firstPointerId });
            if (event.currentTarget.hasPointerCapture?.(firstPointerId)) {
              event.currentTarget.releasePointerCapture(firstPointerId);
            }
            pointerCandidateRef.current = null;
            suppressDragClickRef.current = true;
          }
          suppressPanClickRef.current = true;
          return;
        }
        touchPointers.add(event.pointerId);
      }

      const isMouse = event.pointerType === "mouse";
      const middleButton = isMouse && event.button === 1;
      const leftNavigation = isMouse && event.button === 0 && leftPanEnabled;
      const libraryMiddlePan = middleButton && leftPanEnabled;
      const manualMiddlePan = middleButton && !leftPanEnabled;

      if (leftNavigation || libraryMiddlePan) {
        navigationPointerRef.current = event.pointerId;
        pointerCandidateRef.current = null;
        event.stopPropagation();
        return;
      }
      if (manualMiddlePan) {
        middlePanRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
        navigationPointerRef.current = event.pointerId;
        setIsDragging(true);
        event.currentTarget.setPointerCapture?.(event.pointerId);
        event.preventDefault();
        event.stopPropagation();
        return;
      }

      if (suppressClickAfterDrag && (event.pointerType !== "mouse" || event.button === 0)) {
        pointerCandidateRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
      }
      activeToolPointersRef.current.add(event.pointerId);
      if (event.pointerType !== "mouse" || event.button === 0) {
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }
      onPointerDown?.(event);
    };

    const handleViewportPointerMove = (event) => {
      if (event.pointerType === "touch" && touchPinchingRef.current) return;
      if (middlePanRef.current?.pointerId === event.pointerId) {
        const previous = middlePanRef.current;
        const deltaX = event.clientX - previous.x;
        const deltaY = event.clientY - previous.y;
        middlePanRef.current = { ...previous, x: event.clientX, y: event.clientY };
        if (Math.hypot(deltaX, deltaY) >= 0.5) {
          controls.panBy(deltaX, deltaY, 0);
          suppressPanClickRef.current = true;
        }
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (navigationPointerRef.current === event.pointerId) {
        event.stopPropagation();
        return;
      }
      const candidate = pointerCandidateRef.current;
      if (candidate?.pointerId === event.pointerId
        && Math.hypot(event.clientX - candidate.x, event.clientY - candidate.y) >= 4) {
        candidate.moved = true;
      }
      onPointerMove?.(event);
    };

    const finishPointer = (event, cancelled = false) => {
      if (event.pointerType === "touch") {
        const touchPointers = touchPointersRef.current;
        const wasPinching = touchPinchingRef.current;
        touchPointers.delete(event.pointerId);
        if (wasPinching) {
          activeToolPointersRef.current.delete(event.pointerId);
          if (touchPointers.size === 0) {
            touchPinchingRef.current = false;
            clearClickSuppressionSoon();
          }
          return;
        }
      }
      if (middlePanRef.current?.pointerId === event.pointerId) {
        middlePanRef.current = null;
        navigationPointerRef.current = null;
        setIsDragging(false);
        event.currentTarget.releasePointerCapture?.(event.pointerId);
        clearClickSuppressionSoon();
        event.preventDefault?.();
        event.stopPropagation();
        return;
      }
      if (navigationPointerRef.current === event.pointerId) {
        navigationPointerRef.current = null;
        event.stopPropagation();
      } else if (cancelled) {
        onPointerCancel?.(event);
      } else {
        onPointerUp?.(event);
      }
      activeToolPointersRef.current.delete(event.pointerId);
      if (pointerCandidateRef.current?.pointerId === event.pointerId) {
        if (!cancelled && pointerCandidateRef.current.moved) suppressDragClickRef.current = true;
        pointerCandidateRef.current = null;
        if (suppressDragClickRef.current) clearClickSuppressionSoon();
      }
    };

    const handleViewportClick = (event) => {
      if (suppressPanClickRef.current || suppressDragClickRef.current) {
        suppressPanClickRef.current = false;
        suppressDragClickRef.current = false;
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      onClick?.(event);
    };

    const zoomAroundCenter = (factor) => {
      const frame = frameRef.current;
      if (!frame) return;
      const rect = frame.getBoundingClientRect();
      const nextScale = clampScale(currentScale * factor);
      controls.zoomToPoint(nextScale, rect.left + rect.width / 2, rect.top + rect.height / 2, 0);
    };

    const resetView = () => controls.resetTransform(180, "easeOut");
    const percentage = `${Math.round(currentScale * 100)} %`;
    const roundedScale = Math.round(currentScale * 100) / 100;
    const frame = frameRef.current;
    const centeredX = frame ? Math.max(0, (frame.clientWidth - fitSize.width) / 2) : 0;
    const centeredY = frame ? Math.max(0, (frame.clientHeight - fitSize.height) / 2) : 0;
    const isAtFit = roundedScale === MIN_SCALE
      && Math.abs(controls.instance.state.positionX - centeredX) < 0.5
      && Math.abs(controls.instance.state.positionY - centeredY) < 0.5;

    return (
      <div className="zoomable-viewport__frame" ref={frameRef}>
        <TransformComponent
          wrapperClass={wrapperClass}
          contentClass="zoomable-viewport__transform"
          wrapperStyle={{ width: "100%", height: "100%" }}
          contentStyle={{ width: "fit-content", height: "fit-content" }}
          wrapperProps={{
            onWheel: handleWheel,
            onPointerDown: handleViewportPointerDown,
            onPointerMove: handleViewportPointerMove,
            onPointerUp: (event) => finishPointer(event),
            onPointerCancel: (event) => finishPointer(event, true),
            onClick: handleViewportClick,
          }}
        >
          <div
            ref={attachSurfaceRef}
            className="zoom-image-content"
            style={{ width: fitSize.width || undefined, height: fitSize.height || undefined }}
          >
            <img
              ref={attachImageRef}
              className={`zoom-image ${imageClassName}`.trim()}
              src={src}
              alt={alt}
              draggable="false"
              decoding="async"
              onLoad={handleImageLoad}
              onError={onError}
              style={{
                width: fitSize.width || undefined,
                height: fitSize.height || undefined,
                maxWidth: "none",
                maxHeight: "none",
                visibility: fitSize.width && fitSize.height ? "visible" : "hidden",
              }}
            />
            {children}
          </div>
        </TransformComponent>
        {fitSize.width > 0 && fitSize.height > 0 && (
          <div
            className={`zoomable-viewport__controls${showZoomControls ? "" : " is-auto-hidden"}`}
            role="group"
            aria-label="Controles de zoom"
          >
            <button
              type="button"
              className="zoomable-viewport__button zoomable-viewport__icon-button"
              aria-label="Alejar"
              title="Alejar"
              disabled={roundedScale <= MIN_SCALE}
              onClick={() => zoomAroundCenter(1 / 1.2)}
            ><Minus size={15} aria-hidden="true" /></button>
            <span className="zoomable-viewport__percentage" aria-live="polite" aria-label={`Zoom ${percentage}`}>
              {percentage}
            </span>
            <button
              type="button"
              className="zoomable-viewport__button zoomable-viewport__icon-button"
              aria-label="Acercar"
              title="Acercar"
              disabled={roundedScale >= MAX_SCALE}
              onClick={() => zoomAroundCenter(1.2)}
            ><Plus size={15} aria-hidden="true" /></button>
            <button
              type="button"
              className="zoomable-viewport__button zoomable-viewport__fit-button"
              aria-label="Encajar imagen en el visor"
              title="Encajar imagen"
              disabled={isAtFit}
              onClick={resetView}
            ><Maximize2 size={13} aria-hidden="true" /></button>
          </div>
        )}
      </div>
    );
  };

  return (
    <div
      className={`zoomable-viewport ${className}`.trim()}
      onPointerMove={revealZoomControls}
      onPointerDown={revealZoomControls}
      onFocusCapture={revealZoomControls}
    >
      <TransformWrapper
        initialScale={MIN_SCALE}
        initialPositionX={0}
        initialPositionY={0}
        minScale={MIN_SCALE}
        maxScale={MAX_SCALE}
        centerZoomedOut
        centerOnInit
        limitToBounds
        smooth={false}
        wheel={{ disabled: true }}
        panning={{
          disabled: !canPanWithLeft,
          allowLeftClickPan: true,
          allowMiddleClickPan: true,
          allowRightClickPan: false,
          velocityDisabled: true,
        }}
        pinch={{ disabled: false, allowPanning: true }}
        doubleClick={{ disabled: !allowDoubleClick, mode: "zoomIn", step: 0.65, animationTime: 120 }}
        onTransform={handleTransform}
        onPanningStart={handlePanningStart}
        onPanning={handlePanning}
        onPanningStop={handlePanningStop}
      >
        {renderViewport}
      </TransformWrapper>
    </div>
  );
}
