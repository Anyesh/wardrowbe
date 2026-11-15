const AI_ROUTES = ['/dashboard/suggest', '/dashboard/pairings', '/dashboard/learning'];

export function isAiRoute(pathname: string): boolean {
  return AI_ROUTES.some((route) => pathname === route || pathname.startsWith(route + '/'));
}
