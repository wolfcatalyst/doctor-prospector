import { useSettings } from "./useSettings";

/** True unless the user turned data warnings off in Settings > Preferences. */
export function useShowDataFlags(): boolean {
  const { data } = useSettings();
  return data?.defaults?.show_data_flags ?? true;
}
