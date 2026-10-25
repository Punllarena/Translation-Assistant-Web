import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
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

/** Archive and unarchive one series; the library lists refetch after either. */
export function useArchive(seriesId: number) {
  const queryClient = useQueryClient();
  const path = { params: { path: { series_id: seriesId } } };
  return {
    archive: useMutation({
      mutationFn: () => call(api.POST("/series/{series_id}/archive", path)),
      onSuccess: () => invalidateLibrary(queryClient),
    }),
    unarchive: useMutation({
      mutationFn: () => call(api.POST("/series/{series_id}/unarchive", path)),
      onSuccess: () => invalidateLibrary(queryClient),
    }),
  };
}
