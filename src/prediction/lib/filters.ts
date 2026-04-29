export function liquidityFilter(ev: any): boolean {
  return !!(ev.price && ev.price > 0 && ev.volume && ev.volume > 0);
}
