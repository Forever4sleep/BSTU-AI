import { Component, StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import "./index.css";

/** Показываем текст вместо пустого белого экрана при ошибке в корне приложения */
class BootErrorBoundary extends Component<{ children: ReactNode }, { err: unknown }> {
  state = { err: null as unknown };

  static getDerivedStateFromError(err: unknown) {
    return { err };
  }

  render() {
    const { err } = this.state;
    if (err != null) {
      const msg = err instanceof Error ? err.message + (err.stack ? "\n\n" + err.stack : "") : String(err);
      return (
        <div
          style={{
            minHeight: "100vh",
            padding: "1.5rem",
            fontFamily: "system-ui, sans-serif",
            background: "#0c1220",
            color: "#eef2ff",
            boxSizing: "border-box",
          }}
        >
          <h1 style={{ marginTop: 0, fontSize: "1.25rem" }}>Не удалось запустить приложение</h1>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: "0.85rem", opacity: 0.95 }}>
            {msg}
          </pre>
          <p style={{ opacity: 0.65, fontSize: "0.9rem" }}>Если проблема повторяется, обратитесь к преподавателю или администратору.</p>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BootErrorBoundary>
      <App />
    </BootErrorBoundary>
  </StrictMode>,
);
