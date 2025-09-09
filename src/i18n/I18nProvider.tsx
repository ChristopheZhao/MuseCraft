"use client";

import React, { createContext, useContext, useMemo, useState } from 'react';
import { dictionaries, zh, Language } from './translations';

type I18nContextType = {
  lang: Language;
  t: (key: string) => string;
  setLang: (lang: Language) => void;
};

const I18nContext = createContext<I18nContextType>({
  lang: 'zh',
  t: (k: string) => k,
  setLang: () => {},
});

export const I18nProvider: React.FC<{ defaultLang?: Language; children: React.ReactNode }> = ({
  defaultLang = 'zh',
  children,
}) => {
  const [lang, setLang] = useState<Language>(defaultLang);

  const t = useMemo(() => {
    const dict = dictionaries[lang] || zh;
    return (key: string) => dict[key] ?? key;
  }, [lang]);

  return (
    <I18nContext.Provider value={{ lang, t, setLang }}>
      {children}
    </I18nContext.Provider>
  );
};

export function useI18n() {
  return useContext(I18nContext);
}

