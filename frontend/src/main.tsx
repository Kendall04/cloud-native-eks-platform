import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { readConfig } from "./api";
import "./style.css";
const config = readConfig(import.meta.env);
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App mode={config.mode} base={config.base} />
    </BrowserRouter>
  </React.StrictMode>,
);
