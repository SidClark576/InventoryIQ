import { useCallback } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";

const SHEET_KEYS = ["item", "new"] as const;

type SheetState = { sheet?: boolean } | null;

/** Pass as `state` on links that open a sheet, so closing it pops that history entry. */
export const SHEET_LINK_STATE = { sheet: true } as const;

function withoutSheet(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of SHEET_KEYS) next.delete(key);
  return next;
}

function searchOf(params: URLSearchParams): string {
  const text = params.toString();
  return text ? `?${text}` : "";
}

/**
 * Item detail and "add item" live in the URL (`?item=<id>`, `?new=1`) so refresh
 * and Back work. Opening pushes a history entry; closing pops it when we pushed it,
 * otherwise (deep link, refresh) it replaces the URL without the sheet keys.
 */
export function useSheetParams() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const itemID = params.get("item");
  const isNew = params.get("new") === "1";

  const hrefFor = useCallback(
    (key: (typeof SHEET_KEYS)[number], value: string) => {
      const next = withoutSheet(params);
      next.set(key, value);
      return { pathname: location.pathname, search: searchOf(next) };
    },
    [params, location.pathname],
  );

  const openItem = useCallback(
    (id: string) => navigate(hrefFor("item", id), { state: SHEET_LINK_STATE }),
    [navigate, hrefFor],
  );

  const openNew = useCallback(() => navigate(hrefFor("new", "1"), { state: SHEET_LINK_STATE }), [navigate, hrefFor]);

  const close = useCallback(() => {
    if ((location.state as SheetState)?.sheet) {
      navigate(-1);
      return;
    }
    setParams(withoutSheet(params), { replace: true });
  }, [location.state, navigate, params, setParams]);

  return { itemID, isNew, openItem, openNew, close, itemHref: (id: string) => hrefFor("item", id) };
}
