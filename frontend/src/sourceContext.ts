import { createContext, useContext } from "react";

export interface SourceTarget {
  documentId: string;
  passageId: string | null;
  role: string;
}

export const SourceContext = createContext<(t: SourceTarget) => void>(() => {});
export const useOpenSource = () => useContext(SourceContext);
