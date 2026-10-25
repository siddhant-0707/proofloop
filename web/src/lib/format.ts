export const people = (n: number) => Math.round(n).toLocaleString();
export const dollars = (n: number) => `$${Math.round(n).toLocaleString()}`;
export const percent = (fraction: number) => `${Math.round(fraction * 100)}%`;
export const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
/** "a", "a and b", "a, b and c". */
export const join = (items: string[]) =>
  items.length < 2 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
