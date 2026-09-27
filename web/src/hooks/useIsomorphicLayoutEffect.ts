import { useEffect, useLayoutEffect } from "react";

/** useLayoutEffect on the client (runs before paint), a silent no-op-equivalent on the
 *  server, where React warns about useLayoutEffect. */
export const useIsomorphicLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;
