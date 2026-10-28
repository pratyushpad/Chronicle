/** Thrown when the API answers 503 (database suspended, timing out, or refreshing).
 *  Next keeps a custom string `digest` on a server error, and strips the message in
 *  production, so the digest is the only marker the error boundary can still read. */
export const API_UNAVAILABLE_DIGEST = "API_UNAVAILABLE";

export class ApiUnavailableError extends Error {
  digest = API_UNAVAILABLE_DIGEST;
  constructor(message: string) {
    super(message);
    this.name = "ApiUnavailableError";
  }
}

export function isApiUnavailable(error: { digest?: string; name?: string }): boolean {
  return error.digest === API_UNAVAILABLE_DIGEST || error.name === "ApiUnavailableError";
}
