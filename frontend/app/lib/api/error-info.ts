interface ApiResult {
  error: unknown;
  response?: { status: number } | null;
}

interface AxiosLikeError {
  response?: { status?: number; data?: { detail?: { message?: string } } };
}

/**
 * The status and server message of a failed request. The request helpers drop the response when a call fails,
 * so both live on the axios error (`detail.message` is the backend's ErrorResponse).
 */
export function apiErrorInfo(result: ApiResult): { status?: number; message?: string } {
  const failure = result.error as AxiosLikeError | null | undefined;
  return {
    status: failure?.response?.status ?? result.response?.status,
    message: failure?.response?.data?.detail?.message,
  };
}
