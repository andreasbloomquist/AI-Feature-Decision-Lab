import { createContext, useContext } from "react";
import type { AppConfig } from "./types";

/** Server configuration (roles, launch criteria, versions), loaded once by App. */
export const ConfigContext = createContext<AppConfig | null>(null);
export const useConfig = () => useContext(ConfigContext);
