const dictionaries = {
  en: () => import("../messages/en.json").then((module) => module.default),
  zh: () => import("../messages/zh.json").then((module) => module.default)
};

export type Locale = keyof typeof dictionaries;

export async function getDictionary(locale: string) {
  return dictionaries[(locale as Locale) in dictionaries ? (locale as Locale) : "en"]();
}

export function translate(dictionary: Record<string, unknown>, key: string): string {
  return key.split(".").reduce<unknown>((value, part) => {
    if (value && typeof value === "object" && part in value) {
      return (value as Record<string, unknown>)[part];
    }
    return undefined;
  }, dictionary) as string || key;
}
