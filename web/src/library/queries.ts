import { useQuery, type QueryClient } from "@tanstack/react-query";
import { api, call } from "../api/client";

export const useDocuments = () =>
  useQuery({ queryKey: ["documents"], queryFn: () => call(api.GET("/documents")) });

export const useSeriesList = () =>
  useQuery({ queryKey: ["series"], queryFn: () => call(api.GET("/series")) });

export const useAllVolumes = () =>
  useQuery({ queryKey: ["volumes"], queryFn: () => call(api.GET("/volumes")) });

/** After any library write: the documents, series and volumes lists refetch. */
export function invalidateLibrary(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ["documents"] }),
    queryClient.invalidateQueries({ queryKey: ["series"] }),
    queryClient.invalidateQueries({ queryKey: ["volumes"] }),
  ]);
}
