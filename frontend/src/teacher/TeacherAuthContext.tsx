import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { TEACHER_STORAGE_KEY } from "./authStorage";

type TeacherAuthValue = {
  apiKey: string;
  setApiKey: (k: string) => void;
  clearSession: () => void;
};

const TeacherAuthContext = createContext<TeacherAuthValue | null>(null);

export function TeacherAuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKeyState] = useState(() => localStorage.getItem(TEACHER_STORAGE_KEY) ?? "");

  const setApiKey = useCallback((k: string) => {
    setApiKeyState(k);
    if (k) localStorage.setItem(TEACHER_STORAGE_KEY, k);
    else localStorage.removeItem(TEACHER_STORAGE_KEY);
  }, []);

  const clearSession = useCallback(() => setApiKey(""), []);

  const value = useMemo(
    () => ({ apiKey, setApiKey, clearSession }),
    [apiKey, setApiKey, clearSession],
  );

  return <TeacherAuthContext.Provider value={value}>{children}</TeacherAuthContext.Provider>;
}

export function useTeacherAuth() {
  const ctx = useContext(TeacherAuthContext);
  if (!ctx) throw new Error("useTeacherAuth: нет TeacherAuthProvider");
  return ctx;
}
