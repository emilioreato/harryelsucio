import { api } from "../services/api.js";

export default function CheckpointViewer({ checkpoint, jobId, running, incomplete }) {
  if (!checkpoint || !jobId) {
    return (
      <div className="checkpoint-empty" role="status">
        <span className="empty-mark" aria-hidden="true">◌</span>
        <strong>{running ? "Preparando la primera imagen" : "La evolución aparecerá aquí"}</strong>
        <span>{running ? "La ejecución continúa mientras se prepara la pareja alineada." : "Carga una pareja True Color + SWIR e inicia la segmentación."}</span>
      </div>
    );
  }

  return (
    <div className="checkpoint-viewer" aria-label={`Checkpoint ${checkpoint.label}`}>
      <div className="checkpoint-toolbar">
        <span className="checkpoint-view-kicker">EVOLUCIÓN</span>
        <strong>{checkpoint.label}</strong>
        <span className={`checkpoint-state${incomplete ? " is-incomplete" : ""}`}>
          {running ? "En ejecución" : incomplete ? "Resultado incompleto" : "Vista histórica"}
        </span>
      </div>
      <div className="checkpoint-image-stage">
        <img
          key={checkpoint.id}
          src={`${api.checkpointUrl(jobId, checkpoint.id)}?v=${encodeURIComponent(checkpoint.id)}`}
          alt={`${checkpoint.label}. ${checkpoint.description}`}
          decoding="async"
        />
      </div>
      <p className="checkpoint-description">{checkpoint.description}</p>
    </div>
  );
}
