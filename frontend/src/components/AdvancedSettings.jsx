const KMEANS_FIELDS = [
  ["swir_red", "Predominio rojo SWIR", 1.25],
  ["swir_chroma", "Cromaticidad SWIR", 0.18],
  ["true_green", "Verdor True Color", -0.62],
  ["true_luminance", "Luminosidad True Color", -0.22],
  ["swir_luminance", "Luminosidad SWIR", -0.12],
  ["true_chroma", "Cromaticidad True Color", 0.1],
  ["swir_red_green", "Rojo sobre verde SWIR", 0.22],
  ["true_blue", "Predominio azul True Color", -0.3],
];

const SWIR_FIELDS = [
  ["seed_red", "Semilla · rojo SWIR", 0.8, 0.9999],
  ["grow_red", "Crecimiento · rojo SWIR", 0.5, 0.98],
  ["seed_red_green", "Semilla · rojo/verde", 0.4, 0.99],
  ["grow_red_green", "Crecimiento · rojo/verde", 0.3, 0.98],
  ["vegetation_max", "Límite de verdor True Color", 0.5, 1],
];

const WATER_FIELDS = [
  ["true_color_darkness", "Oscuridad True Color · percentil", 0.2],
  ["swir_darkness", "Oscuridad SWIR · percentil", 0.1],
  ["swir_red_max", "Máximo rojo SWIR · percentil", 0.55],
  ["swir_red_green_max", "Máximo rojo/verde SWIR · percentil", 0.55],
];

function Slider({ label, value, onChange }) {
  return (
    <div>
      <div className="range-row">
        <label className="field-label">{label}</label>
        <output className="range-value">{Math.round(Number(value) * 100)} %</output>
      </div>
      <input
        className="range-control"
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

function NumericField({ label, value, min, max, step = 0.01, onChange, placeholder }) {
  return (
    <label className="tuning-field">
      <span>{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))}
      />
    </label>
  );
}

export default function AdvancedSettings({ value, onChange, onReset, method }) {
  const updateGroup = (group, key, nextValue) => {
    onChange({
      ...value,
      [group]: { ...value[group], [key]: nextValue },
    });
  };
  const updateTop = (key, nextValue) => onChange({ ...value, [key]: nextValue });
  const hasKMeans = ["kmeans", "fusion_ponderada"].includes(method);
  const hasSwir = ["swir_histeresis", "fusion_ponderada"].includes(method);

  return (
    <details className="details-panel developer-settings">
      <summary>Herramientas de desarrollo</summary>
      <div className="developer-content">
        <p className="field-help">
          Ajustes experimentales. Los scores ayudan a comparar hipótesis; no son probabilidades calibradas.
        </p>

        {method === "fusion_ponderada" && (
          <details className="tuning-group">
            <summary>Ponderación entre algoritmos</summary>
            <div className="tuning-content">
              <p className="field-help">Los pesos se normalizan por su suma. El umbral indica cuánto voto hace falta.</p>
              <Slider label="Peso K-Means" value={value.fusion_kmeans_weight} onChange={(n) => updateTop("fusion_kmeans_weight", n)} />
              <Slider label="Peso SWIR + histéresis" value={value.fusion_swir_weight} onChange={(n) => updateTop("fusion_swir_weight", n)} />
              <Slider label="Voto mínimo" value={value.fusion_threshold} onChange={(n) => updateTop("fusion_threshold", n)} />
            </div>
          </details>
        )}

        {hasKMeans && (
          <details className="tuning-group">
            <summary>Score de K-Means</summary>
            <div className="tuning-content tuning-grid">
              {KMEANS_FIELDS.map(([key, label, defaultValue]) => (
                <NumericField
                  key={key}
                  label={label}
                  value={value.kmeans_weights[key]}
                  min={-3}
                  max={3}
                  step={0.05}
                  onChange={(n) => updateGroup("kmeans_weights", key, n ?? defaultValue)}
                />
              ))}
              <p className="field-help tuning-note">
                Positivo favorece esa señal en el score; negativo la penaliza. Se normalizan por escena.
              </p>
            </div>
          </details>
        )}

        {hasSwir && (
          <details className="tuning-group">
            <summary>Percentiles SWIR e histéresis</summary>
            <div className="tuning-content tuning-grid">
              {SWIR_FIELDS.map(([key, label, min, max]) => (
                <NumericField
                  key={key}
                  label={label}
                  value={value.swir_thresholds[key]}
                  min={min}
                  max={max}
                  step={0.001}
                  placeholder="Automático"
                  onChange={(n) => updateGroup("swir_thresholds", key, n)}
                />
              ))}
              <p className="field-help tuning-note">
                Vacío adapta el umbral a la sensibilidad y al histograma. Una semilla mayor exige una señal más intensa.
              </p>
            </div>
          </details>
        )}

        <details className="tuning-group">
          <summary>Detección de humo</summary>
          <div className="tuning-content">
            <p className="field-help">Los pesos combinan cian SWIR, luminosidad y neutralidad en True Color.</p>
            <Slider label="Firma cian SWIR" value={value.smoke_weights.cyan} onChange={(n) => updateGroup("smoke_weights", "cyan", n)} />
            <Slider label="Luminosidad True Color" value={value.smoke_weights.luminance} onChange={(n) => updateGroup("smoke_weights", "luminance", n)} />
            <Slider label="Neutralidad True Color" value={value.smoke_weights.neutrality} onChange={(n) => updateGroup("smoke_weights", "neutrality", n)} />
            <Slider label="Confianza mínima" value={value.smoke_threshold} onChange={(n) => updateTop("smoke_threshold", n)} />
          </div>
        </details>

        <details className="tuning-group">
          <summary>Veto de agua entre las dos vistas</summary>
          <div className="tuning-content tuning-grid">
            {WATER_FIELDS.map(([key, label]) => (
              <NumericField
                key={key}
                label={label}
                value={value.water_thresholds[key]}
                min={0.01}
                max={0.99}
                step={0.01}
                onChange={(n) => updateGroup("water_thresholds", key, n ?? 0.5)}
              />
            ))}
            <p className="field-help tuning-note">
              El veto exige oscuridad concordante en ambas imágenes y ausencia de rojo SWIR. Percentiles bajos son más restrictivos.
            </p>
          </div>
        </details>

        <button className="text-button reset-tuning" type="button" onClick={onReset}>
          Restablecer ajustes finos
        </button>
      </div>
    </details>
  );
}
