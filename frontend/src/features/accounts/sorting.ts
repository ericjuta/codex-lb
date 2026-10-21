import type { AccountSummary } from "@/features/accounts/schemas";
import type { AccountQuotaDisplayPreference } from "@/hooks/use-account-quota-display";
import { normalizeStatus, type DashboardAccountStatus } from "@/utils/account-status";
import { parseDate } from "@/utils/formatters";

export type AccountSortMode =
  | "reset_soonest"
  | "reset_latest"
  | "name_asc"
  | "name_desc"
  | "most_reset_credits"
  | "status_asc"
  | "status_desc"
  | "quota_5h_asc"
  | "quota_5h_desc"
  | "quota_7d_asc"
  | "quota_7d_desc"
  | "quota_monthly_asc"
  | "quota_monthly_desc";

export const ACCOUNT_SORT_OPTIONS: readonly { value: AccountSortMode; label: string }[] = [
  { value: "reset_soonest", label: "Reset time (soonest)" },
  { value: "reset_latest", label: "Reset time (latest)" },
  { value: "most_reset_credits", label: "Most reset credits" },
  { value: "name_asc", label: "Name (A-Z)" },
  { value: "name_desc", label: "Name (Z-A)" },
  { value: "status_asc", label: "Status (active first)" },
  { value: "status_desc", label: "Status (inactive first)" },
  { value: "quota_5h_asc", label: "5h quota (lowest remaining)" },
  { value: "quota_5h_desc", label: "5h quota (highest remaining)" },
  { value: "quota_7d_asc", label: "Weekly quota (lowest remaining)" },
  { value: "quota_7d_desc", label: "Weekly quota (highest remaining)" },
  { value: "quota_monthly_asc", label: "Monthly quota (lowest remaining)" },
  { value: "quota_monthly_desc", label: "Monthly quota (highest remaining)" },
] as const;

export const DEFAULT_ACCOUNT_SORT_MODE: AccountSortMode = "most_reset_credits";

type KeyedSortMode = Extract<AccountSortMode, `status_${string}` | `quota_${string}`>;

const STATUS_SORT_ORDER: Record<DashboardAccountStatus, number> = {
  active: 0,
  paused: 1,
  limited: 2,
  exceeded: 3,
  reauth: 4,
  deactivated: 5,
};

function isKeyedSortMode(sortMode: AccountSortMode): sortMode is KeyedSortMode {
  return sortMode.startsWith("status_") || sortMode.startsWith("quota_");
}

/** Sort key for status/quota modes; unknown quota is +Infinity so it always sorts last. */
function keyedSortValue(account: AccountSummary, sortMode: KeyedSortMode): number {
  switch (sortMode) {
    case "status_asc":
    case "status_desc":
      return STATUS_SORT_ORDER[normalizeStatus(account.status)];
    case "quota_5h_asc":
    case "quota_5h_desc":
      return account.usage?.primaryRemainingPercent ?? Number.POSITIVE_INFINITY;
    case "quota_7d_asc":
    case "quota_7d_desc":
      return account.usage?.secondaryRemainingPercent ?? Number.POSITIVE_INFINITY;
    case "quota_monthly_asc":
    case "quota_monthly_desc":
      return account.usage?.monthlyRemainingPercent ?? Number.POSITIVE_INFINITY;
  }
}

function visibleQuotaResetTimestamps(
  account: AccountSummary,
  quotaDisplay: AccountQuotaDisplayPreference,
): number[] {
  const now = Date.now();
  const hasPrimary = account.windowMinutesPrimary != null || account.usage?.primaryRemainingPercent != null || account.resetAtPrimary != null;
  const hasSecondary = account.windowMinutesSecondary != null || account.usage?.secondaryRemainingPercent != null || account.resetAtSecondary != null;
  const showPrimary = hasPrimary && (quotaDisplay !== "weekly" || !hasSecondary);
  const showSecondary = hasSecondary && (quotaDisplay !== "5h" || !hasPrimary);

  return [
    showPrimary ? parseDate(account.resetAtPrimary)?.getTime() ?? Number.POSITIVE_INFINITY : Number.POSITIVE_INFINITY,
    showSecondary ? parseDate(account.resetAtSecondary)?.getTime() ?? Number.POSITIVE_INFINITY : Number.POSITIVE_INFINITY,
  ].filter((resetAt) => resetAt > now);
}

function accountSortLabel(account: AccountSummary): string {
  return (account.displayName || account.email || account.accountId).trim().toLowerCase();
}

function accountResetTimestamp(account: AccountSummary, quotaDisplay: AccountQuotaDisplayPreference): number {
  const resets = visibleQuotaResetTimestamps(account, quotaDisplay);
  return resets.length > 0 ? Math.min(...resets) : Number.POSITIVE_INFINITY;
}

/** Orders finite values by direction; non-finite (unknown) values sort last in both directions. */
function compareKnownNumbers(left: number, right: number, direction: "asc" | "desc"): number {
  const leftFinite = Number.isFinite(left);
  const rightFinite = Number.isFinite(right);
  if (leftFinite !== rightFinite) {
    return leftFinite ? -1 : 1;
  }
  if (left === right) {
    return 0;
  }
  return direction === "desc" ? right - left : left - right;
}

function resetCreditNearestExpiry(account: AccountSummary): number {
  const parsed = parseDate(account.resetCreditNearestExpiresAt);
  return parsed ? parsed.getTime() : Number.POSITIVE_INFINITY;
}

function compareByResetCredits(left: AccountSummary, right: AccountSummary): number {
  const leftCount = left.availableResetCredits ?? 0;
  const rightCount = right.availableResetCredits ?? 0;
  if (leftCount !== rightCount) {
    return rightCount - leftCount;
  }
  // Tiebreak by soonest expiry ascending; null expiry (Infinity) sorts last.
  return compareKnownNumbers(
    resetCreditNearestExpiry(left),
    resetCreditNearestExpiry(right),
    "asc",
  );
}

export function sortAccountsForDisplay(
  accounts: AccountSummary[],
  quotaDisplay: AccountQuotaDisplayPreference,
  sortMode: AccountSortMode = DEFAULT_ACCOUNT_SORT_MODE,
): AccountSummary[] {
  return accounts
    .slice()
    .sort((left, right) => {
      if (isKeyedSortMode(sortMode)) {
        const keyedComparison = compareKnownNumbers(
          keyedSortValue(left, sortMode),
          keyedSortValue(right, sortMode),
          sortMode.endsWith("_desc") ? "desc" : "asc",
        );
        if (keyedComparison !== 0) {
          return keyedComparison;
        }
      } else if (sortMode === "most_reset_credits") {
        const creditComparison = compareByResetCredits(left, right);
        if (creditComparison !== 0) {
          return creditComparison;
        }
      } else if (sortMode === "reset_latest" || sortMode === "reset_soonest") {
        const leftReset = accountResetTimestamp(left, quotaDisplay);
        const rightReset = accountResetTimestamp(right, quotaDisplay);
        const resetComparison = compareKnownNumbers(
          leftReset,
          rightReset,
          sortMode === "reset_latest" ? "desc" : "asc",
        );
        if (resetComparison !== 0) {
          return resetComparison;
        }
      } else {
        const leftLabel = accountSortLabel(left);
        const rightLabel = accountSortLabel(right);
        const labelComparison = sortMode === "name_asc"
          ? leftLabel.localeCompare(rightLabel)
          : rightLabel.localeCompare(leftLabel);
        if (labelComparison !== 0) {
          return labelComparison;
        }
      }

      const leftReset = accountResetTimestamp(left, quotaDisplay);
      const rightReset = accountResetTimestamp(right, quotaDisplay);
      const resetComparison = compareKnownNumbers(leftReset, rightReset, "asc");
      if (resetComparison !== 0) {
        return resetComparison;
      }
      const labelComparison = accountSortLabel(left).localeCompare(accountSortLabel(right));
      if (labelComparison !== 0) {
        return labelComparison;
      }
      return left.accountId.localeCompare(right.accountId);
    });
}
