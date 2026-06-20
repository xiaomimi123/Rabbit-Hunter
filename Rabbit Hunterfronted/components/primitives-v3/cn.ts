/** Tiny class joiner. Filters out falsy values. Avoids needing clsx as a dep. */
export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}

/** Card class — matches cryptoquant-ai dashboard style: rounded 3xl + shadow + backdrop blur. */
export function cardClassName(extra?: string): string {
  return cn(
    'rounded-3xl border border-zinc-800 bg-zinc-900/70 p-5 shadow-[0_24px_80px_rgba(0,0,0,0.25)] backdrop-blur',
    extra,
  );
}
