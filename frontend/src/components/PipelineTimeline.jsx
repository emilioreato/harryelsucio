import { useRef } from "react";

function checkpointPosition(checkpoint) {
  const value = Number(checkpoint.progress);
  return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
}

export default function PipelineTimeline({
  checkpoints = [],
  progress = 0,
  running = false,
  jobId,
  selectedCheckpointId,
  followingLive,
  checkpointWarnings = [],
  onSelectCheckpoint,
  onFollowLive,
}) {
  const dragging = useRef(false);
  const selectedIndex = checkpoints.findIndex((item) => item.id === selectedCheckpointId);
  const selected = selectedIndex >= 0 ? checkpoints[selectedIndex] : null;
  const latest = checkpoints.at(-1) || null;

  const selectFromPointer = (event) => {
    if (!checkpoints.length) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const target = Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100));
    const closest = checkpoints.reduce((best, item, index) => {
      const distance = Math.abs(checkpointPosition(item) - target);
      return distance < best.distance ? { index, distance } : best;
    }, { index: 0, distance: Infinity });
    onSelectCheckpoint(checkpoints[closest.index].id);
  };

  const handlePointerDown = (event) => {
    if (!checkpoints.length || event.target.closest("button")) return;
    dragging.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    selectFromPointer(event);
  };

  const handlePointerMove = (event) => {
    if (dragging.current) selectFromPointer(event);
  };

  const handlePointerUp = (event) => {
    dragging.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  return (
    <section className="pipeline-timeline" aria-label="Evolución de la segmentación">
      <div className="timeline-heading">
        <span>{running ? "Etapas del análisis" : "Historial del análisis"}</span>
        {checkpoints.length > 0 && <span className="timeline-count">← → · {checkpoints.length} {checkpoints.length === 1 ? "etapa" : "etapas"}</span>}
      </div>
      <div className="timeline-rail" aria-label="Navegación de checkpoints">
        <div className="progress-track timeline-progress" aria-hidden="true">
          <span style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
        </div>
        <div
          className="timeline-scrubber"
          role="slider"
          tabIndex={checkpoints.length ? 0 : -1}
          aria-label="Checkpoint visual seleccionado"
          aria-valuemin={checkpoints.length ? 1 : 0}
          aria-valuemax={checkpoints.length || 0}
          aria-valuenow={checkpoints.length ? Math.max(1, selectedIndex + 1) : 0}
          aria-valuetext={selected ? `${selected.label}, etapa ${selectedIndex + 1} de ${checkpoints.length}` : "Sin capturas disponibles"}
          aria-keyshortcuts="ArrowLeft ArrowRight Home End"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        />
        <div className="timeline-markers">
          {checkpoints.map((checkpoint, index) => (
            <button
              key={checkpoint.id}
              className={`timeline-marker${checkpoint.id === selectedCheckpointId ? " is-selected" : ""}${checkpoint.final ? " is-final" : ""}`}
              style={{ left: `${checkpointPosition(checkpoint)}%` }}
              type="button"
              disabled={!jobId}
              aria-label={`Mostrar checkpoint ${index + 1}: ${checkpoint.label}. ${checkpoint.description}`}
              aria-pressed={checkpoint.id === selectedCheckpointId}
              title={`${checkpoint.label} · ${checkpoint.description}`}
              onClick={() => onSelectCheckpoint(checkpoint.id)}
            >
              <span />
            </button>
          ))}
        </div>
      </div>
      <div className="timeline-detail" aria-live="polite">
        <div className="timeline-selected-copy">
          <strong>{selected?.label || (running ? "Esperando la primera captura" : "Sin etapas disponibles")}</strong>
          <span>{selected?.description || (running ? "La imagen preparada aparecerá en cuanto termine su lectura." : "Inicia una segmentación para crear un historial visual.")}</span>
        </div>
        <button
          className={`follow-live-button${followingLive ? " is-following" : ""}`}
          type="button"
          disabled={!latest || (followingLive && selected?.id === latest.id)}
          aria-pressed={followingLive}
          onClick={onFollowLive}
        >
          {followingLive ? "Siguiendo en vivo" : "Seguir en vivo"}
        </button>
      </div>
      {checkpointWarnings.length > 0 && (
        <p className="timeline-warning" role="status">No se pudieron guardar {checkpointWarnings.length} captura(s); el análisis continúa.</p>
      )}
    </section>
  );
}
