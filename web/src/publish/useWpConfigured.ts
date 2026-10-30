import { useQuery } from "@tanstack/react-query";
import { api, call } from "../api/client";

/** Whether the user has a usable WordPress credential — the rule of `publish.wp_config`:
 *  kind `wordpress`, the unnamed row, and an endpoint. `GET /credentials` is cheap and already
 *  loaded on the settings page. `undefined` while loading; callers treat that as not configured
 *  for hiding, so nothing flashes in and out. */
export function useWpConfigured(): boolean | undefined {
  const credentials = useQuery({
    queryKey: ["wp", "credentials"],
    queryFn: () => call(api.GET("/credentials")),
    staleTime: 60_000,
  });
  if (!credentials.isSuccess) return undefined;
  return credentials.data.some(
    (c) => c.kind === "wordpress" && c.name === "" && c.endpoint_url !== "",
  );
}
