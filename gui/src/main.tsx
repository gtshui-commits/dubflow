import ReactDOM from "react-dom/client";
import App from "./App";

// NOTE: React.StrictMode is intentionally omitted - its dev double-mount
// breaks imperative libraries like wavesurfer.js (empty waveform render).
ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
