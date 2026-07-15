import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

export type AdvancedSettingsGroupProps = {
  children: ReactNode;
};

/**
 * Collapsed-by-default container for power-user settings sections.
 *
 * Children are unmounted until first expansion, so section-owned data queries
 * stay deferred. After that, they remain mounted while hidden so in-flight
 * mutation observers and local form state survive collapse/reopen cycles.
 */
export function AdvancedSettingsGroup({ children }: AdvancedSettingsGroupProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen) {
      setHasOpened(true);
    }
  };

  return (
    <Collapsible open={open} onOpenChange={handleOpenChange} className="rounded-xl border bg-card">
      <CollapsibleTrigger
        aria-label={open ? t("settings.advanced.hide") : t("settings.advanced.show")}
        className="flex w-full items-center gap-3 rounded-xl p-5 text-left transition-colors hover:bg-muted/40"
      >
        <ChevronRight
          aria-hidden="true"
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
            open && "rotate-90",
          )}
        />
        <span className="min-w-0">
          <span className="block text-sm font-semibold tracking-tight">
            {t("settings.advanced.title")}
          </span>
          <span className="mt-0.5 block text-xs text-muted-foreground">
            {t("settings.advanced.description")}
          </span>
        </span>
      </CollapsibleTrigger>
      {hasOpened ? (
        <CollapsibleContent
          forceMount
          hidden={!open}
          className="space-y-4 border-t p-4"
        >
          {children}
        </CollapsibleContent>
      ) : null}
    </Collapsible>
  );
}
