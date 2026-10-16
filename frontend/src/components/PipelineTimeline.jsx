import { useRef } from "react";

function checkpointPosition(index, count) {
  return count < 2 ? 50 : (index / (count - 1)) * 100;
}

export default function PipelineTimeline({
  checkpoints = [],
  jobId,
  selectedCheckpointId,
  checkpointWarnings = [],
  onSelectCheckpoint,
}) {
  const dragging = useRef(false);
  const selectedIndex = checkpoints.findIndex((item) => item.id === selectedCheckpointId);
  const selected = selectedIndex >= 0 ? checkpoints[selectedIndex] : null;
  const selectFromPointer = (event) => {
    if (!checkpoints.length) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const target = Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100));
    const index = Math.round((target / 100) * (checkpoints.length - 1));
    onSelectCheckpoint(checkpoints[index].id);
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
        <span className="timeline-title">Etapas de la segmentación</span>
      </div>
      {checkpoints.length > 0 && (
        <>
          <div className="timeline-rail" aria-label="Navegación de checkpoints">
            <div className="timeline-track" aria-hidden="true" />
            <div
              className="timeline-scrubber"
              role="slider"
              tabIndex={0}
              aria-label="Checkpoint visual seleccionado"
              aria-valuemin={1}
              aria-valuemax={checkpoints.length}
              aria-valuenow={Math.max(1, selectedIndex + 1)}
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
                  style={{ left: `${checkpointPosition(index, checkpoints.length)}%` }}
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
          {selected && (
            <div className="timeline-detail" aria-live="polite">
              <div className="timeline-selected-copy">
                <strong>{selected.label}</strong>
                <span>{selected.description}</span>
              </div>
            </div>
          )}
        </>
      )}
      {checkpointWarnings.length > 0 && (
        <p className="timeline-warning" role="status">No se pudieron guardar {checkpointWarnings.length} captura(s); el análisis continúa.</p>
      )}
    </section>
  );
}
