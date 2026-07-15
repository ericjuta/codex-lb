import { QueryClient, QueryClientProvider, useMutation } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AdvancedSettingsGroup } from "@/features/settings/components/advanced-settings-group";

function renderGroup(mutationPromise: Promise<void>) {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });

  function MutationSection() {
    const mutation = useMutation({ mutationFn: () => mutationPromise });

    return (
      <button
        type="button"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? "Saving planner" : "Save planner"}
      </button>
    );
  }

  return render(
    <QueryClientProvider client={queryClient}>
      <AdvancedSettingsGroup>
        <MutationSection />
      </AdvancedSettingsGroup>
    </QueryClientProvider>,
  );
}

describe("AdvancedSettingsGroup", () => {
  it("retains a pending section mutation across collapse and reopen", async () => {
    let resolveMutation!: () => void;
    const mutationPromise = new Promise<void>((resolve) => {
      resolveMutation = resolve;
    });
    const user = userEvent.setup({ delay: null });

    renderGroup(mutationPromise);

    expect(screen.queryByRole("button", { name: "Save planner" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show advanced settings" }));
    await user.click(screen.getByRole("button", { name: "Save planner" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Saving planner" })).toBeDisabled();
    });

    await user.click(screen.getByRole("button", { name: "Hide advanced settings" }));
    expect(screen.queryByRole("button", { name: "Saving planner" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show advanced settings" }));
    expect(screen.getByRole("button", { name: "Saving planner" })).toBeDisabled();

    resolveMutation();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save planner" })).toBeEnabled();
    });
  });
});
