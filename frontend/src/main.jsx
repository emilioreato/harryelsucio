import React from "react";
import { createRoot } from "react-dom/client";
import { Theme } from "@radix-ui/themes";
import App from "./App.jsx";
import "@radix-ui/themes/styles.css";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Theme appearance="light" accentColor="blue" grayColor="slate" radius="large" scaling="95%">
      <App />
    </Theme>
  </React.StrictMode>,
);
