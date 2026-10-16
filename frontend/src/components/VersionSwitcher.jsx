export default function VersionSwitcher({ version, onChange }) {
  return (
    <div className="version-switcher-wrap">
      <div className="version-switcher" role="tablist" aria-label="Retos de Lumbre">
        {[
          ["basic", "Básico"],
          ["advanced", "Avanzado"],
        ].map(([id, label]) => (
          <button
            key={id}
            className={`version-switcher-tab${version === id ? " is-active" : ""}`}
            type="button"
            role="tab"
            aria-selected={version === id}
            onClick={() => onChange(id)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
