import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { Streamlit } from "streamlit-component-lib";
import { RedactionViewer } from "./RedactionViewer";
import type { RedactionViewerProps } from "./types";
import "./styles.css";

/**
 * Functional wrapper that subscribes to Streamlit render events directly.
 *
 * We avoid StreamlitComponentBase and withStreamlitConnection because both
 * call Streamlit.setFrameHeight() (auto-detect) on every componentDidUpdate,
 * which fights with our explicit setFrameHeight in onImageLoad and creates
 * an infinite re-render loop.
 */
function App() {
  const [args, setArgs] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    console.log("[RV] Component mounted, registering RENDER_EVENT listener");
    let renderCount = 0;
    const onRender = (event: Event) => {
      renderCount++;
      console.log(`[RV] RENDER_EVENT #${renderCount}`);
      const detail = (event as CustomEvent).detail;
      setArgs(detail.args);
    };

    Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
    Streamlit.setComponentReady();
    console.log("[RV] setComponentReady called");

    return () => {
      console.log("[RV] Component unmounting");
      Streamlit.events.removeEventListener(Streamlit.RENDER_EVENT, onRender);
    };
  }, []);

  if (!args) {
    console.log("[RV] No args yet, rendering null");
    return null;
  }

  const props: RedactionViewerProps = {
    imageDataUrl: args["imageDataUrl"],
    marks: args["marks"] || [],
    scale: args["scale"],
    pageWidthPt: args["pageWidthPt"],
    pageHeightPt: args["pageHeightPt"],
    mode: args["mode"] || "draw",
    caseClosed: args["caseClosed"] || false,
    privilegeColors: args["privilegeColors"] || {},
    zoomPct: args["zoomPct"] || 75,
  };

  return <RedactionViewer {...props} />;
}

const root = ReactDOM.createRoot(document.getElementById("root") as HTMLElement);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
