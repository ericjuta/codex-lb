import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImportDialog } from "@/features/accounts/components/import-dialog";
import { useAccountMutations } from "@/features/accounts/hooks/use-accounts";
import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/utils";

const { toastSuccess, toastError } = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: toastSuccess,
    error: toastError,
  },
}));

function Harness({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  const { importMutation } = useAccountMutations();
  return (
    <ImportDialog
      open
      busy={importMutation.isPending}
      onOpenChange={onOpenChange}
      onImport={(files) => importMutation.mutateAsync(files)}
    />
  );
}

function authFile(name: string) {
  return new File(["{}"], name, { type: "application/json" });
}

describe("ImportDialog multi-file import", () => {
  beforeEach(() => {
    toastSuccess.mockClear();
    toastError.mockClear();
  });

  it("imports selected files sequentially, refreshes once and closes when all succeed", async () => {
    const user = userEvent.setup();
    let calls = 0;
    let inFlight = 0;
    let maxInFlight = 0;
    server.use(
      http.post("/api/accounts/import", async () => {
        calls += 1;
        const call = calls;
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        await new Promise((resolve) => setTimeout(resolve, 5));
        inFlight -= 1;
        return HttpResponse.json({
          accountId: `acc_${call}`,
          email: `acc-${call}@example.com`,
          planType: "plus",
          status: "active",
        });
      }),
    );
    const onOpenChange = vi.fn();
    const { queryClient } = renderWithProviders(<Harness onOpenChange={onOpenChange} />);
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    await user.upload(screen.getByLabelText("Files"), [authFile("one.json"), authFile("two.json")]);
    expect(screen.getByText("one.json")).toBeInTheDocument();
    expect(screen.getByText("two.json")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(calls).toBe(2);
    expect(maxInFlight).toBe(1);
    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(toastSuccess).toHaveBeenCalledWith("2 accounts imported");
    expect(toastError).not.toHaveBeenCalled();
    expect(invalidateSpy.mock.calls.filter(([filters]) => filters?.queryKey?.join("/") === "accounts/list")).toHaveLength(1);
  });

  it("continues past a failed file, reports it per file and keeps only the failed file selected", async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      // jsdom drops the uploaded file's name and bytes from the multipart body, so the 2nd request is the one for bad.json.
      http.post("/api/accounts/import", async () => {
        calls += 1;
        if (calls === 2) {
          return HttpResponse.json(
            { error: { code: "invalid_auth_json", message: "Invalid auth.json payload" } },
            { status: 400 },
          );
        }
        return HttpResponse.json({
          accountId: `acc_${calls}`,
          email: `acc-${calls}@example.com`,
          planType: "plus",
          status: "active",
        });
      }),
    );
    const onOpenChange = vi.fn();
    const { queryClient } = renderWithProviders(<Harness onOpenChange={onOpenChange} />);
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    await user.upload(screen.getByLabelText("Files"), [
      authFile("first.json"),
      authFile("bad.json"),
      authFile("last.json"),
    ]);
    await user.click(screen.getByRole("button", { name: "Import" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("bad.json: Invalid auth.json payload");
    expect(calls).toBe(3);
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.queryByText("first.json")).not.toBeInTheDocument();
    expect(screen.queryByText("last.json")).not.toBeInTheDocument();
    expect(screen.getAllByText("bad.json")).not.toHaveLength(0);
    expect(toastSuccess).toHaveBeenCalledWith("2 accounts imported");
    expect(toastError).toHaveBeenCalledWith("Invalid auth.json payload");
    expect(invalidateSpy.mock.calls.filter(([filters]) => filters?.queryKey?.join("/") === "accounts/list")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Import" })).toBeEnabled();
  });

  it("does not refresh when every file fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("/api/accounts/import", () =>
        HttpResponse.json({ error: { code: "invalid_auth_json", message: "Invalid auth.json payload" } }, { status: 400 }),
      ),
    );
    const { queryClient } = renderWithProviders(<Harness onOpenChange={vi.fn()} />);
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    await user.upload(screen.getByLabelText("Files"), [authFile("a.json"), authFile("b.json")]);
    await user.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith("2 files failed to import"));
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("a.json: Invalid auth.json payload");
    expect(screen.getByRole("alert")).toHaveTextContent("b.json: Invalid auth.json payload");
  });
});
