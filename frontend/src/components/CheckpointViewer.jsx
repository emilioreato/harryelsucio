import { api } from "../services/api.js";
import ZoomableImageViewport from "./ZoomableImageViewport.jsx";

export default function CheckpointViewer({ checkpoint, jobId, running, incomplete }) {
  if (!checkpoint || !jobId) {
    return (
      <div className="checkpoint-empty" role="status">
        <span className="empty-mark" aria-hidden="true">◌</span>
        <strong>{running ? "Preparando la primera imagen" : "Inicia la segmentación."}</strong>
        {running && <span>La ejecución continúa mientras se prepara la pareja alineada.</span>}
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
        <ZoomableImageViewport
          className="zoomable-viewport--checkpoint"
          imageClassName="checkpoint-image"
          src={`${api.checkpointUrl(jobId, checkpoint.id)}?v=${encodeURIComponent(checkpoint.id)}`}
          alt={`${checkpoint.label}. ${checkpoint.description}`}
          resetKey={jobId}
        />
      </div>
      <p className="checkpoint-description">{checkpoint.description}</p>
    </div>
  );
}
