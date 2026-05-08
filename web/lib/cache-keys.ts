export function buildPlayerCacheKey(name: string): string {
  return name.trim().toLowerCase();
}

export function buildPositionCacheKey(position: string): string {
  return position.trim().toLowerCase();
}
