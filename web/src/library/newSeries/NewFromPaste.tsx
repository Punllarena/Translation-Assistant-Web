import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, call } from "../../api/client";
import { invalidateLibrary } from "../queries";
import { EMPTY_FIELDS, seriesBody, type SeriesFieldsValue } from "./fields";
import SeriesFields from "./SeriesFields";

export default function NewFromPaste() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [value, setValue] = useState<SeriesFieldsValue>(EMPTY_FIELDS);
  const create = useMutation({
    mutationFn: (v: SeriesFieldsValue) => call(api.POST("/series", { body: { ...seriesBody(v), syosetu_url: "" } })),
    onSuccess: async (s) => {
      await invalidateLibrary(queryClient);
      navigate(`/series/${s.id}`);
    },
  });
  const blank = value.title.trim() === "";
  return (
    <form className="panel pad" onSubmit={(e) => { e.preventDefault(); if (!blank && !create.isPending) create.mutate(value); }}>
      <h2 className="sec">Paste</h2>
      <p className="muted">Start empty and paste chapters in yourself.</p>
      <SeriesFields value={value} onChange={setValue} disabled={create.isPending} />
      {create.error && <p className="error" role="alert">{create.error.message}</p>}
      <div className="row-fields">
        <button type="submit" className="primary" disabled={blank || create.isPending}>Create</button>
      </div>
    </form>
  );
}
