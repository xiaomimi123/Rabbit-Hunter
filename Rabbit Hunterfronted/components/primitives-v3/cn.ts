/** Tiny class joiner. Filters out falsy values. Avoids needing clsx as a dep. */
export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}

/** Card class — Field Instrument tokens. Hairline border, surface background, subtle elevation. */
export function cardClassName(extra?: string): string {
  return cn(
    'rounded-md border border-hairline bg-bg-surface p-5 shadow-[0_18px_60px_rgba(0,0,0,0.30)]',
    extra,
  );
}
