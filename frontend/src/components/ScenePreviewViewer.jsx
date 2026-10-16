import { useEffect, useState } from "react";
import ZoomableImageViewport from "./ZoomableImageViewport.jsx";

export default function ScenePreviewViewer({ scene, src, running }) {
  const [imageError, setImageError] = useState(false);

  useEffect(() => setImageError(false), [scene?.id, src]);

  return (
    <div className="checkpoint-viewer scene-preview-viewer" aria-label={`Vista previa de ${scene.label}`}>
      <div className="checkpoint-toolbar">
        <span className="checkpoint-view-kicker">{running ? "ENTRADA" : "ESCENA"}</span>
        <strong>{scene.label}</strong>
        <span className="checkpoint-state">{running ? "Preparando análisis" : "True Color · original"}</span>
      </div>
      <div className="checkpoint-image-stage scene-preview-stage">
        {imageError ? (
          <div className="checkpoint-empty" role="status">
            <strong>No se pudo cargar la imagen</strong>
            <span>Comprueba que la escena siga disponible y vuelve a seleccionarla.</span>
          </div>
        ) : (
          <ZoomableImageViewport
            className="zoomable-viewport--checkpoint"
            imageClassName="scene-preview-image"
            src={src}
            alt={`Imagen True Color original de ${scene.label}`}
            resetKey={`preview:${scene.id}`}
            onError={() => setImageError(true)}
          />
        )}
      </div>
      <p className="checkpoint-description">
        {running
          ? "Imagen True Color de entrada. Aquí aparecerán las etapas conforme avance la segmentación."
          : "Vista previa de la imagen True Color con la que se analizará esta escena."}
      </p>
    </div>
  );
}
