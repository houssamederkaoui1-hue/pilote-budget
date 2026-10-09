import { useCallback, useState } from "react";

import { ApiError } from "../lib/api";

/**
 * Minimal mutation hook: pending/error state around a single async call.
 *
 * The argument type is carried by the factory so call sites stay typed:
 * ``useMutation((id: number) => apiDelete(`/categories/${id}`))``.
 */
export function useMutation<TArgs, TResult>(
  run: (args: TArgs) => Promise<TResult>,
): {
  mutate: (args: TArgs) => Promise<TResult>;
  pending: boolean;
  error: string | null;
  reset: () => void;
} {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutate = useCallback(
    async (args: TArgs): Promise<TResult> => {
      setPending(true);
      setError(null);
      try {
        const result = await run(args);
        return result;
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Unexpected error";
        setError(message);
        throw err;
      } finally {
        setPending(false);
      }
    },
    [run],
  );

  const reset = useCallback(() => setError(null), []);

  return { mutate, pending, error, reset };
}

/** Extract a readable message from any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unexpected error";
}
