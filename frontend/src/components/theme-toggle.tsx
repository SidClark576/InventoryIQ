import { DesktopIcon, MoonIcon, SunIcon } from "@phosphor-icons/react";
import { useTheme } from "next-themes";
import {
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";

const OPTIONS = [
  { value: "light", label: "Light", Icon: SunIcon },
  { value: "dark", label: "Dark", Icon: MoonIcon },
  { value: "system", label: "System", Icon: DesktopIcon },
] as const;

/** Light / Dark / System radio items. Render inside any DropdownMenuContent. */
export function ThemeRadioGroup() {
  const { theme = "system", setTheme } = useTheme();

  return (
    <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(String(v))}>
      {OPTIONS.map(({ value, label, Icon }) => (
        <DropdownMenuRadioItem key={value} value={value}>
          <Icon />
          {label}
        </DropdownMenuRadioItem>
      ))}
    </DropdownMenuRadioGroup>
  );
}
